from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import vlm
from app.visual_calibration import validate_prediction


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


if __name__ == "__main__":
    unittest.main()
