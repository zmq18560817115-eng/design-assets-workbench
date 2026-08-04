from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import vlm
from app.visual_calibration import PRIMARY_TEXT_MODULE_TYPES, validate_prediction


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "evaluation" / "visual-analysis" / "untitled1-manifest.json"
COMPARISON = ROOT / "evaluation" / "visual-analysis" / "version-comparison.json"


def region(kind: str, x: float, y: float, width: float, height: float, ident: str = "r"):
    return {
        "id": ident,
        "type": kind,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def truth(*, product=True, text=False, layout=False):
    return {
        "product_regions": [
            {"type": "product_image", "normalized": {"x": .1, "y": .2, "width": .4, "height": .5}}
        ] if product else [],
        "primary_text_regions": [
            {"type": "main_text", "normalized": {"x": .1, "y": .05, "width": .8, "height": .1}}
        ] if text else [],
        "layout_modules": [
            {"type": "layout_block", "normalized": {"x": .05, "y": .05, "width": .9, "height": .9}}
        ] if layout else [],
        "allowed_overlap_relations": [],
    }


class VisualCalibrationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_01_manifest_has_expected_real_asset_counts(self):
        self.assertEqual(self.manifest["total_scanned"], 56)
        self.assertEqual(self.manifest["split_counts"]["calibration"], 24)
        self.assertEqual(self.manifest["split_counts"]["holdout"], 6)

    def test_02_only_verified_calibration_contains_ground_truth(self):
        with_truth = [item for item in self.manifest["assets"] if "ground_truth" in item]
        self.assertEqual(len(with_truth), 24)
        self.assertTrue(all(item["dataset_split"] == "calibration" for item in with_truth))
        self.assertTrue(all(item["annotation_status"] == "verified" for item in with_truth))

    def test_03_holdout_is_sealed_and_contains_no_answer(self):
        holdout = [item for item in self.manifest["assets"] if item["dataset_split"] == "holdout"]
        self.assertEqual(len(holdout), 6)
        self.assertTrue(self.manifest["holdout_sealed"])
        self.assertTrue(all("ground_truth" not in item for item in holdout))

    def test_04_asset_has_exactly_one_split(self):
        ids = [item["asset_id"] for item in self.manifest["assets"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(
            item["dataset_split"] in {"calibration", "holdout", "unassigned"}
            for item in self.manifest["assets"]
        ))

    def test_05_product_missed_has_canonical_error_code(self):
        result = validate_prediction(
            {"blueprint_modules": [region("main_title", .1, .05, .8, .1)]},
            truth(product=True),
        )
        self.assertIn("PRODUCT_MISSED", result["error_codes"])

    def test_06_sibling_overlap_is_rejected(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .1, .1, .6, .6, "a"),
                region("main_title", .12, .12, .6, .6, "b"),
            ]},
            truth(product=False),
        )
        self.assertIn("MODULE_OVERLAP_INVALID", result["error_codes"])

    def test_07_parent_child_containment_is_not_false_positive(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("layout_block", .05, .05, .9, .9, "parent"),
                region("product_image", .2, .2, .3, .4, "child"),
            ]},
            truth(product=False),
        )
        self.assertNotIn("MODULE_OVERLAP_INVALID", result["error_codes"])

    def test_08_duplicate_module_is_rejected(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("main_title", .1, .1, .8, .1, "a"),
                region("main_title", .1, .1, .8, .1, "b"),
            ]},
            truth(product=False),
        )
        self.assertEqual(result["metrics"]["duplicate_module_count"], 1)
        self.assertIn("MODULE_OVERLAP_INVALID", result["error_codes"])

    def test_09_out_of_bounds_has_canonical_error_code(self):
        result = validate_prediction(
            {"blueprint_modules": [region("product_image", .8, .1, .4, .5)]},
            truth(product=False),
        )
        self.assertIn("MODULE_OUT_OF_BOUNDS", result["error_codes"])

    def test_10_invalid_schema_is_rejected(self):
        result = validate_prediction({}, truth())
        self.assertFalse(result["schema_valid"])
        self.assertEqual(result["error_codes"], ["OUTPUT_SCHEMA_INVALID"])

    def test_11_model_payload_is_bounded_for_large_png(self):
        image = Image.new("RGB", (2600, 1800), "white")
        output = io.BytesIO()
        image.save(output, "PNG")
        prepared, mime = vlm._model_image_payload(output.getvalue(), "image/png")
        with Image.open(io.BytesIO(prepared)) as resized:
            self.assertLessEqual(max(resized.size), 1600)
        self.assertEqual(mime, "image/jpeg")

    def test_12_failed_gates_do_not_freeze_or_allow_holdout(self):
        comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
        self.assertEqual(comparison["dataset_split"], "calibration")
        self.assertFalse(comparison["holdout_executed"])
        self.assertFalse(comparison["calibration_passed"])
        self.assertFalse(comparison["candidate_frozen"])
        self.assertFalse(comparison["holdout_allowed"])

    def test_13_report_builder_rejects_holdout_input(self):
        module_path = ROOT / "backend" / "scripts" / "build_visual_calibration_report.py"
        spec = importlib.util.spec_from_file_location("calibration_report", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "holdout.json"
            path.write_text(
                json.dumps({"dataset_split": "holdout", "holdout_executed": True}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                module.load_calibration(path)

    def test_14_primary_text_child_counts_inside_reviewed_text_group(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("main_title", .3, .07, .4, .05, "title"),
            ]},
            truth(product=False, text=True),
        )
        self.assertEqual(result["metrics"]["primary_text_hit_count"], 1)
        self.assertNotIn("PRIMARY_TEXT_MISSED", result["error_codes"])

    def test_15_product_box_cannot_impersonate_layout_block(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .05, .05, .9, .9, "product"),
            ]},
            truth(product=False, layout=True),
        )
        self.assertEqual(result["metrics"]["layout_hit_count"], 0)
        self.assertIn("LAYOUT_MODULE_MISSED", result["error_codes"])

    def test_16_all_supported_text_types_match_main_text(self):
        for text_type in ("main_title", "subtitle", "selling_point", "body_text"):
            with self.subTest(text_type=text_type):
                result = validate_prediction(
                    {"blueprint_modules": [
                        region(text_type, .1, .05, .8, .1, text_type),
                    ]},
                    truth(product=False, text=True),
                )
                self.assertEqual(result["metrics"]["primary_text_hit_count"], 1)

    def test_17_one_prediction_cannot_match_two_truth_boxes(self):
        ground_truth = truth(product=False)
        ground_truth["primary_text_regions"] = [
            {"type": "main_text", "normalized": {"x": .1, "y": .05, "width": .8, "height": .1}},
            {"type": "main_text", "normalized": {"x": .1, "y": .08, "width": .8, "height": .1}},
        ]
        result = validate_prediction(
            {"blueprint_modules": [region("main_title", .1, .05, .8, .13)]},
            ground_truth,
        )
        self.assertEqual(result["metrics"]["primary_text_hit_count"], 1)

    def test_18_zero_layout_recall_cannot_report_perfect_type_accuracy(self):
        module_path = ROOT / "backend" / "scripts" / "run_visual_calibration.py"
        spec = importlib.util.spec_from_file_location("run_visual_calibration", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        row = {
            "run_status": "completed", "schema_valid": True,
            "elapsed_ms": 1, "error_codes": ["LAYOUT_MODULE_MISSED"],
            "metrics": {
                "product_truth_count": 0, "product_hit_count": 0,
                "primary_text_truth_count": 0, "primary_text_hit_count": 0,
                "layout_truth_count": 2, "layout_hit_count": 0,
                "matched_type_count": 0, "evaluable_module_count": 2,
            },
        }
        metrics = module.aggregate([row])
        self.assertEqual(metrics["layout_module_recall"], 0)
        self.assertEqual(metrics["module_type_accuracy"], 0)

    def test_19_failed_canary_quality_blocks_full_calibration(self):
        module_path = ROOT / "backend" / "scripts" / "run_visual_calibration.py"
        spec = importlib.util.spec_from_file_location("run_visual_calibration_gate", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        metrics = {
            "total": 3, "task_success_rate": 1, "schema_valid_rate": 1,
            "product_detection_rate": 1, "primary_text_detection_rate": .66,
            "layout_module_recall": 0, "invalid_overlap_rate": 0,
            "timeout_rate": 0,
        }
        report = {
            "report_kind": "calibration_canary", "dataset_split": "calibration",
            "holdout_executed": False, "metrics": metrics,
            "quality_gates": {"primary_text_detection_rate": False},
            "quality_passed": False, "fallback_count": 0,
        }
        self.assertFalse(module.full_calibration_ready(report))

    def test_20_v2_and_v3_reports_cannot_mix(self):
        module_path = ROOT / "backend" / "scripts" / "run_visual_calibration.py"
        spec = importlib.util.spec_from_file_location("run_visual_calibration_versions", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertFalse(module.report_versions_match(
            {"prompt_version": "visual-calibration-prompt-v2",
             "validator_version": "visual-calibration-validator-v2"},
            {"prompt_version": "visual-calibration-prompt-v3",
             "validator_version": "visual-calibration-validator-v3"},
        ))

    def test_21_v3_contract_defines_logical_unbordered_blocks(self):
        prompt = (ROOT / "evaluation" / "visual-analysis" /
                  "prompt-visual-calibration-v3.txt").read_text(encoding="utf-8")
        self.assertIn("不要求真实边框", prompt)
        self.assertIn("可包含产品和文字", prompt)
        self.assertIn("相同类型高度重合的框只保留一个", prompt)

    def test_22_calibration_runner_has_no_holdout_stage(self):
        source = (ROOT / "backend" / "scripts" /
                  "run_visual_calibration.py").read_text(encoding="utf-8")
        self.assertIn('choices=("canary", "full")', source)
        self.assertNotIn('choices=("canary", "full", "holdout")', source)

    def test_23_validation_does_not_mutate_verified_ground_truth(self):
        ground_truth = truth(product=False, text=True, layout=True)
        before = json.dumps(ground_truth, sort_keys=True)
        validate_prediction(
            {"blueprint_modules": [
                region("main_title", .1, .05, .8, .1),
                region("layout_block", .05, .05, .9, .9),
            ]}, ground_truth,
        )
        self.assertEqual(json.dumps(ground_truth, sort_keys=True), before)

    def test_24_canary_requires_perfect_product_detection(self):
        from app.visual_calibration import canary_gate_results
        metrics = {
            "task_success_rate": 1, "schema_valid_rate": 1,
            "product_detection_rate": .95, "primary_text_detection_rate": 1,
            "layout_module_recall": 1, "invalid_overlap_rate": 0,
            "timeout_rate": 0,
        }
        self.assertFalse(canary_gate_results(metrics)["product_detection_rate"])

    def test_25_feature_list_spatial_match_counts_as_main_text(self):
        parsed = {"blueprint_modules": [
            region("feature_list", .1, .05, .8, .1, "features"),
        ]}
        result = validate_prediction(parsed, truth(product=False, text=True))
        self.assertEqual(result["metrics"]["primary_text_hit_count"], 1)
        self.assertEqual(
            result["metrics"]["primary_text_matches"][0]["prediction_type"],
            "feature_list",
        )
        self.assertEqual(parsed["blueprint_modules"][0]["type"], "feature_list")

    def test_26_feature_list_without_spatial_match_does_not_count(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("feature_list", .1, .7, .8, .1, "features"),
            ]},
            truth(product=False, text=True),
        )
        self.assertEqual(result["metrics"]["primary_text_hit_count"], 0)

    def test_27_one_feature_list_cannot_match_two_main_text_boxes(self):
        ground_truth = truth(product=False)
        ground_truth["primary_text_regions"] = [
            {"type": "main_text", "normalized": {"x": .1, "y": .05, "width": .8, "height": .1}},
            {"type": "main_text", "normalized": {"x": .1, "y": .08, "width": .8, "height": .1}},
        ]
        result = validate_prediction(
            {"blueprint_modules": [
                region("feature_list", .1, .05, .8, .13, "features"),
            ]}, ground_truth,
        )
        self.assertEqual(result["metrics"]["primary_text_hit_count"], 1)

    def test_28_non_primary_types_never_match_main_text(self):
        excluded = {
            "logo", "price", "cta", "footnote", "decoration", "background",
            "product_image", "person_image", "scene_image", "layout_block",
            "parameter_table",
        }
        self.assertTrue(excluded.isdisjoint(PRIMARY_TEXT_MODULE_TYPES))
        for module_type in excluded:
            with self.subTest(module_type=module_type):
                result = validate_prediction(
                    {"blueprint_modules": [
                        region(module_type, .1, .05, .8, .1, module_type),
                    ]}, truth(product=False, text=True),
                )
                self.assertEqual(result["metrics"]["primary_text_hit_count"], 0)

    def test_29_offline_revalidation_records_no_model_recall(self):
        module_path = ROOT / "backend" / "scripts" / "revalidate_visual_calibration.py"
        spec = importlib.util.spec_from_file_location("offline_revalidation", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        asset = next(
            item for item in self.manifest["assets"]
            if item.get("dataset_split") == "calibration"
            and "ground_truth" in item
        )
        gt = asset["ground_truth"]
        modules = []
        for index, item in enumerate(gt["product_regions"]):
            modules.append({"id": f"p{index}", "type": "product_image", **item["normalized"]})
        for index, item in enumerate(gt["primary_text_regions"]):
            modules.append({"id": f"t{index}", "type": "feature_list", **item["normalized"]})
        for index, item in enumerate(gt["layout_modules"]):
            modules.append({"id": f"l{index}", "type": "layout_block", **item["normalized"]})
        source = {
            "dataset_split": "calibration", "holdout_executed": False,
            "prompt_version": "visual-calibration-prompt-v3",
            "validator_version": "visual-calibration-validator-v3",
            "runs": [{
                "asset_id": asset["asset_id"], "filename": asset["filename"],
                "run_status": "completed", "elapsed_ms": 1,
                "parsed_output": {"blueprint_modules": modules},
            }],
        }
        report = module.revalidate(
            source, {"assets": [asset]}, {}, source_path="source-v3.json",
            validator_version="visual-calibration-validator-v4",
        )
        self.assertFalse(report["model_recalled"])
        self.assertFalse(report["holdout_read"])
        self.assertEqual(report["source_validator_version"], "visual-calibration-validator-v3")
        self.assertEqual(report["revalidation_validator_version"], "visual-calibration-validator-v4")

    def test_30_validator_v3_remains_unchanged_and_v4_is_separate(self):
        v3 = ROOT / "evaluation" / "visual-analysis" / "validator-visual-calibration-v3.json"
        v4 = ROOT / "evaluation" / "visual-analysis" / "validator-visual-calibration-v4.json"
        self.assertNotEqual(v3.resolve(), v4.resolve())
        self.assertNotIn("primary_text_taxonomy", json.loads(v3.read_text(encoding="utf-8")))
        self.assertEqual(
            json.loads(v4.read_text(encoding="utf-8"))["primary_text_taxonomy"],
            "PRIMARY_TEXT_MODULE_TYPES",
        )

    def test_31_offline_revalidation_does_not_overwrite_source_report(self):
        module_path = ROOT / "backend" / "scripts" / "revalidate_visual_calibration.py"
        source = module_path.read_text(encoding="utf-8")
        self.assertIn("离线复评必须使用独立输出文件", source)
        self.assertNotIn("source_report.write_text", source)

    def test_32_reasonable_contained_decoration_is_legal_overlay(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .1, .1, .8, .8, "host"),
                region("decoration", .2, .2, .5, .5, "overlay"),
            ]}, truth(product=False),
            thresholds={"allow_overlay_containment": True},
        )
        self.assertNotIn("MODULE_OVERLAP_INVALID", result["error_codes"])
        self.assertEqual(result["metrics"]["legal_overlay_count"], 1)
        self.assertEqual(
            result["metrics"]["decoration_host_type_counts"],
            {"product_image": 1},
        )

    def test_33_partially_crossing_decoration_is_illegal(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .1, .1, .5, .5, "host"),
                region("decoration", .5, .5, .3, .3, "overlay"),
            ]}, truth(product=False),
            thresholds={"allow_overlay_containment": True},
        )
        self.assertIn("MODULE_OVERLAP_INVALID", result["error_codes"])
        self.assertEqual(result["metrics"]["illegal_overlay_count"], 1)

    def test_34_cross_type_near_duplicate_is_illegal(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .1, .1, .8, .8, "host"),
                region("decoration", .1, .1, .8, .8, "overlay"),
            ]}, truth(product=False),
            thresholds={"allow_overlay_containment": True},
        )
        self.assertIn("CROSS_TYPE_DUPLICATE", result["error_codes"])
        self.assertIn("MODULE_OVERLAP_INVALID", result["error_codes"])
        self.assertEqual(result["metrics"]["cross_type_duplicate_count"], 1)

    def test_35_background_parent_containment_remains_legal(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("background", .05, .05, .9, .9, "parent"),
                region("product_image", .2, .2, .3, .4, "child"),
            ]}, truth(product=False),
        )
        self.assertNotIn("MODULE_OVERLAP_INVALID", result["error_codes"])

    def test_36_calibration_reuses_formal_overlay_types(self):
        from app import layout_blueprint, visual_calibration
        self.assertIs(visual_calibration.OVERLAY_TYPES, layout_blueprint.OVERLAY_TYPES)
        self.assertEqual(visual_calibration.OVERLAY_TYPES, {"decoration", "background"})

    def test_37_validator_v5_keeps_strict_thresholds(self):
        v4 = json.loads((ROOT / "evaluation" / "visual-analysis" /
                         "validator-visual-calibration-v4.json").read_text(encoding="utf-8"))
        v5 = json.loads((ROOT / "evaluation" / "visual-analysis" /
                         "validator-visual-calibration-v5.json").read_text(encoding="utf-8"))
        for key in ("region_iou", "product_iou", "maximum_sibling_overlap_ratio",
                    "duplicate_module_iou", "containment_exemption_ratio"):
            self.assertEqual(v5[key], v4[key])
        self.assertEqual(v5["cross_type_duplicate_iou"], .9)
        self.assertEqual(v5["overlay_max_area_ratio"], .85)

    def test_38_legal_overlay_uses_one_host_and_other_overlap_stays_ordinary(self):
        result = validate_prediction(
            {"blueprint_modules": [
                region("product_image", .1, .1, .8, .8, "host"),
                region("decoration", .2, .2, .5, .5, "overlay"),
                region("person_image", .0, .6, .3, .3, "person"),
            ]}, truth(product=False),
            thresholds={"allow_overlay_containment": True},
        )
        self.assertNotIn("MODULE_OVERLAP_INVALID", result["error_codes"])
        self.assertEqual(result["metrics"]["legal_overlay_count"], 1)
        self.assertEqual(result["metrics"]["illegal_overlay_count"], 0)


if __name__ == "__main__":
    unittest.main()
