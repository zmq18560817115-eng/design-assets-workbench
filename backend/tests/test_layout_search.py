from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_tmp = tempfile.TemporaryDirectory(prefix="layout-search-p3-test-")
_root = Path(_tmp.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_root / "uploads")
os.environ["VISION_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""

from PIL import Image
from fastapi.testclient import TestClient

from app import config, models
from app.database import SessionLocal
from app.layout_patterns import discover_candidates, structure_similarity
from app.layout_search import (
    SCORING_VERSION,
    evaluation,
    normalized_module_counts,
)
from app.business_taxonomy import normalize_business_value, values_match
from app.main import app


class LayoutSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.db = SessionLocal()
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "layout_search_acceptance.json")
            .read_text(encoding="utf-8")
        )
        cls.groups = fixture["groups"]
        cls.case_ids: list[list[int]] = []
        cls.pattern_ids: list[int] = []
        cls.requirement_ids: list[int] = []
        for group_index, group in enumerate(cls.groups):
            case_ids, blueprint_ids = [], []
            for index in range(4):
                case = models.Case(
                    name=f"P3-{group['key']}-{index}",
                    product_category=group["product_category"],
                    channel=group["channel"],
                    content_type=group["purpose"],
                    campaign_stage="正式投放",
                    business_goal=group["purpose"],
                    summary=f"{group['product_category']} {group['purpose']}",
                    status="public",
                )
                cls.db.add(case)
                cls.db.flush()
                modules = cls.make_modules(group["modules"], index * .002)
                blueprint = models.LayoutBlueprint(
                    case_id=case.id,
                    canvas_ratio=group["canvas_ratio"],
                    orientation=group["orientation"],
                    grid_columns=12 if group["orientation"] == "landscape" else 6,
                    grid_rows=6 if group["orientation"] == "landscape" else 12,
                    reading_flow=(
                        "left-to-right" if group["orientation"] == "landscape"
                        else "top-to-bottom"
                    ),
                    information_density=group["density"],
                    text_image_ratio=.5,
                    module_count=len(modules),
                    modules_json=json.dumps(modules),
                    layout_signature=f"p3-{group['key']}",
                    version=1,
                    review_status="verified",
                    model_name="fixture",
                    prompt_version="fixture-v1",
                    editor="fixture",
                )
                cls.db.add(blueprint)
                cls.db.flush()
                case_ids.append(case.id)
                blueprint_ids.append(blueprint.id)
            pattern = models.LayoutPattern(
                name=f"P3-{group['key']}-pattern",
                pattern_code=f"P3-{group_index}",
                description=f"{group['channel']} {group['purpose']}",
                canvas_ratio=group["canvas_ratio"],
                orientation=group["orientation"],
                grid_columns=12 if group["orientation"] == "landscape" else 6,
                grid_rows=6 if group["orientation"] == "landscape" else 12,
                reading_flow=(
                    "left-to-right" if group["orientation"] == "landscape"
                    else "top-to-bottom"
                ),
                information_density=group["density"],
                modules_json=json.dumps(cls.make_modules(group["modules"])),
                module_structure_json=json.dumps(cls.make_modules(group["modules"])),
                module_count=len(group["modules"]),
                channel_tags=json.dumps([group["channel"]], ensure_ascii=False),
                scene_tags=json.dumps([group["purpose"]], ensure_ascii=False),
                business_goal_tags=json.dumps([group["purpose"]], ensure_ascii=False),
                evidence_case_ids_json=json.dumps(case_ids),
                evidence_blueprint_ids_json=json.dumps(blueprint_ids),
                source_case_ids=json.dumps(case_ids),
                source_blueprint_ids=json.dumps(blueprint_ids),
                evidence_count=4,
                confidence_level="candidate",
                review_status="verified",
                discovery_method="fixture",
                model_name="fixture",
                prompt_version="fixture-v1",
                editor="fixture",
            )
            cls.db.add(pattern)
            cls.db.flush()
            requirement = models.BusinessRequirement(
                title=f"P3需求-{group['key']}",
                product_category=group["product_category"],
                channel=group["channel"],
                content_purpose=group["purpose"],
                campaign_stage="正式投放",
                business_goal=group["purpose"],
                canvas_ratio=group["canvas_ratio"],
                orientation=group["orientation"],
                information_density=group["density"],
                required_modules_json=json.dumps(group["modules"][:3]),
                optional_modules_json="[]",
                forbidden_modules_json="[]",
                style_keywords_json="[]",
                reference_case_ids_json=json.dumps([case_ids[0]]),
                reference_case_ids=json.dumps([case_ids[0]]),
                status="confirmed",
            )
            cls.db.add(requirement)
            cls.db.flush()
            cls.case_ids.append(case_ids)
            cls.pattern_ids.append(pattern.id)
            cls.requirement_ids.append(requirement.id)

        draft_pattern = models.LayoutPattern(
            name="P3-draft-pattern", canvas_ratio="3:4",
            orientation="portrait", review_status="draft",
        )
        disabled_pattern = models.LayoutPattern(
            name="P3-disabled-pattern", canvas_ratio="3:4",
            orientation="portrait", review_status="disabled",
        )
        cls.db.add_all([draft_pattern, disabled_pattern])
        cls.db.flush()
        cls.draft_pattern_id = draft_pattern.id
        cls.disabled_pattern_id = disabled_pattern.id

        unverified_case = models.Case(name="P3-unverified-case", status="public")
        cls.db.add(unverified_case)
        cls.db.flush()
        modules = cls.make_modules(["main_title", "product_image"])
        cls.db.add(models.LayoutBlueprint(
            case_id=unverified_case.id, canvas_ratio="3:4",
            orientation="portrait", grid_columns=6, grid_rows=12,
            reading_flow="top-to-bottom", information_density="medium",
            text_image_ratio=.5, module_count=len(modules),
            modules_json=json.dumps(modules), version=1,
            review_status="ai_generated", model_name="fixture",
        ))
        cls.db.commit()
        cls.unverified_case_id = unverified_case.id
        assert sum(len(value) for value in cls.case_ids) == fixture["case_count"]
        assert len(cls.pattern_ids) == fixture["pattern_count"]
        assert len(cls.requirement_ids) == fixture["requirement_count"]

    @staticmethod
    def make_modules(types: list[str], offset: float = 0) -> list[dict]:
        return [{
            "id": f"{module_type}-{index + 1}",
            "type": module_type,
            "label": module_type,
            "x": round(.05 + (index % 3) * .29 + offset, 4),
            "y": round(.06 + index * .18 + offset, 4),
            "width": .24,
            "height": .11,
            "priority": index + 1,
            "importance": 1,
            "alignment": "center",
            "description": "",
            "content_summary": "",
            "confidence": .95,
        } for index, module_type in enumerate(types)]

    @staticmethod
    def blueprint(types: list[str]) -> SimpleNamespace:
        modules = LayoutSearchTest.make_modules(types)
        return SimpleNamespace(
            modules_json=json.dumps(modules), module_count=len(modules),
            grid_columns=6, grid_rows=12, reading_flow="top-to-bottom",
            layout_signature="same", orientation="portrait",
            canvas_ratio="3:4", information_density="medium",
        )

    def search(self, index=0, **patch):
        payload = {
            "pattern_limit": 10, "case_limit": 20,
            "include_unverified": False, "reanalyze_reference": False,
            **patch,
        }
        response = self.client.post(
            f"/api/business-requirements/{self.requirement_ids[index]}/layout-search",
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.client.__exit__(None, None, None)

    def test_01_only_verified_patterns(self):
        ids = {row["id"] for row in self.search()["patterns"]}
        self.assertNotIn(self.draft_pattern_id, ids)

    def test_02_disabled_pattern_is_excluded(self):
        ids = {row["id"] for row in self.search()["patterns"]}
        self.assertNotIn(self.disabled_pattern_id, ids)

    def test_03_forbidden_module_results_are_excluded(self):
        requirement = self.db.get(models.BusinessRequirement, self.requirement_ids[0])
        requirement.forbidden_modules_json = json.dumps(["cta"])
        self.db.commit()
        result = self.search()
        self.assertNotIn(self.pattern_ids[0], {row["id"] for row in result["patterns"]})
        self.assertIn(self.pattern_ids[0], {row["id"] for row in result["excluded_results"]})
        requirement.forbidden_modules_json = "[]"
        self.db.commit()

    def test_04_missing_required_modules_are_downweighted(self):
        result = self.search(1)
        target = next(row for row in result["patterns"] if row["id"] == self.pattern_ids[0])
        self.assertTrue(target["missing_required_modules"])
        self.assertLess(target["score_breakdown"]["required_modules"], 25)

    def test_05_complete_required_modules_rank_higher(self):
        result = self.search(1)
        self.assertEqual(result["patterns"][0]["id"], self.pattern_ids[1])

    def test_06_module_ids_are_normalized(self):
        counts = normalized_module_counts([
            "selling_point-1", "selling_point-2", "product_image-1"
        ])
        self.assertEqual(counts["selling_point"], 2)
        self.assertEqual(counts["product_image"], 1)

    def test_07_module_counts_affect_structure_similarity(self):
        single = self.blueprint(["main_title", "product_image", "selling_point"])
        triple = self.blueprint([
            "main_title", "product_image", "selling_point",
            "selling_point", "selling_point",
        ])
        self.assertLess(structure_similarity(single, triple)["module_types"], 1)
        self.assertLess(structure_similarity(single, triple)["position_size"], 1)

    def test_08_orientation_affects_ordering(self):
        result = self.search(3)
        self.assertEqual(result["patterns"][0]["id"], self.pattern_ids[3])

    def test_09_canvas_ratio_affects_ordering(self):
        result = self.search(2)
        self.assertEqual(result["patterns"][0]["id"], self.pattern_ids[2])

    def test_10_information_density_affects_ordering(self):
        result = self.search(1)
        target = result["patterns"][0]
        self.assertEqual(target["score_breakdown"]["information_density"], 10)

    def test_11_omitted_fields_do_not_lose_points(self):
        requirement = models.BusinessRequirement(
            title="P3空约束", required_modules_json="[]",
            forbidden_modules_json="[]", style_keywords_json="[]",
        )
        self.db.add(requirement)
        self.db.commit()
        response = self.client.post(
            f"/api/business-requirements/{requirement.id}/layout-search",
            json={"pattern_limit": 10, "case_limit": 20},
        )
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()["patterns"][0]
        self.assertEqual(first["score_breakdown"]["business_scene"], 35)
        self.assertEqual(first["score_breakdown"]["layout_structure"], 20)

    def test_12_breakdown_equals_total(self):
        for row in self.search()["patterns"] + self.search()["cases"]:
            self.assertAlmostEqual(sum(row["score_breakdown"].values()), row["total_score"])

    def test_13_reasons_come_from_real_fields(self):
        reasons = self.search()["patterns"][0]["match_reasons"]
        self.assertTrue(any(reason.startswith("渠道匹配") for reason in reasons))
        self.assertIn("画布方向一致", reasons)

    def test_14_results_are_traceable(self):
        for row in self.search()["patterns"] + self.search()["cases"]:
            self.assertTrue(row["source_case_ids"])
            self.assertTrue(row["source_blueprint_ids"])

    def test_15_reference_image_creates_temporary_blueprint(self):
        path = config.UPLOAD_DIR / "p3-reference.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (600, 800), "#e8eef5").save(path)
        requirement = self.db.get(models.BusinessRequirement, self.requirement_ids[0])
        requirement.reference_image_path = "/uploads/p3-reference.png"
        self.db.commit()
        result = self.search(reanalyze_reference=True)
        self.assertEqual(
            result["search_summary"]["reference_analysis"]["generation_mode"],
            "deterministic_local",
        )

    def test_16_reference_image_does_not_create_case(self):
        before = self.db.query(models.Case).count()
        self.search()
        self.assertEqual(before, self.db.query(models.Case).count())

    def test_17_reference_failure_keeps_basic_search_available(self):
        requirement = self.db.get(models.BusinessRequirement, self.requirement_ids[1])
        requirement.reference_image_path = "/uploads/not-found-p3.png"
        self.db.commit()
        result = self.search(1, reanalyze_reference=True)
        self.assertTrue(result["patterns"])
        self.assertEqual(
            result["search_summary"]["reference_analysis"]["generation_mode"],
            "failed_fallback",
        )

    def test_18_reference_analysis_cache_is_reused(self):
        first = self.search()["search_summary"]["reference_analysis"]["id"]
        second = self.search()["search_summary"]["reference_analysis"]["id"]
        self.assertEqual(first, second)

    def test_19_search_run_snapshot_is_saved(self):
        result = self.search()
        run = self.db.get(models.LayoutSearchRun, result["search_run_id"])
        self.assertIsNotNone(run)
        self.assertEqual(run.scoring_version, SCORING_VERSION)
        self.assertIn("patterns", json.loads(run.result_snapshot_json))

    def test_20_relevance_feedback_is_saved(self):
        result = self.search()
        row = result["patterns"][0]
        response = self.client.post(
            f"/api/layout-search-runs/{result['search_run_id']}/feedback",
            json={
                "result_type": "pattern", "result_id": row["id"],
                "rank": row["rank"], "relevance": "relevant",
                "reviewer": "P3测试负责人", "notes": "fixture正确模式",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.db.get(models.LayoutSearchFeedback, response.json()["id"]).reviewer,
            "P3测试负责人",
        )

    def test_21_precision_and_acceptance_fixture(self):
        version = "fixture-predefined-v1"
        # Freeze labels derived from fixture identities, never from returned ranks.
        for index in range(5):
            split = "calibration" if index < 3 else "holdout"
            for group_index, ids in enumerate(self.case_ids):
                relevance = "relevant" if group_index == index else (
                    "partially_relevant" if group_index == (index + 1) % 5
                    else "irrelevant"
                )
                for result_id in ids:
                    self.db.add(models.LayoutSearchGroundTruth(
                        requirement_id=self.requirement_ids[index],
                        result_type="case", result_id=result_id,
                        expected_relevance=relevance,
                        reviewer="fixture-evaluator",
                        reason=f"fixture group {group_index}",
                        dataset_version=version, dataset_split=split,
                    ))
            for group_index, result_id in enumerate(self.pattern_ids):
                self.db.add(models.LayoutSearchGroundTruth(
                    requirement_id=self.requirement_ids[index],
                    result_type="pattern", result_id=result_id,
                    expected_relevance=(
                        "relevant" if group_index == index else
                        "partially_relevant" if group_index == (index + 1) % 5
                        else "irrelevant"
                    ),
                    reviewer="fixture-evaluator",
                    reason=f"fixture group {group_index}",
                    dataset_version=version, dataset_split=split,
                ))
        self.db.commit()
        response = self.client.post(
            "/api/layout-search/ground-truth/freeze",
            json={"dataset_version": version},
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post(
            "/api/layout-search/evaluation/run",
            json={"dataset_version": version},
        )
        self.assertEqual(response.status_code, 200, response.text)
        report = evaluation(self.db, version)
        self.assertEqual(report["dataset"]["total"], 125)
        self.assertEqual(len(report["overall"]["requirements"]), 5)
        self.assertIn(report["status"], {"passed", "not_ready"})

    def test_22_legacy_match_endpoint_remains_available(self):
        response = self.client.post(
            f"/api/business-requirements/{self.requirement_ids[0]}/match"
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_23_single_and_triple_selling_points_are_not_identical(self):
        left = self.blueprint(["main_title", "product_image", "selling_point"])
        right = self.blueprint([
            "main_title", "product_image", "selling_point",
            "selling_point", "selling_point",
        ])
        self.assertLess(structure_similarity(left, right)["total"], 1)

    def test_24_single_and_double_products_are_not_identical(self):
        left = self.blueprint(["main_title", "product_image"])
        right = self.blueprint(["main_title", "product_image", "product_image"])
        self.assertLess(structure_similarity(left, right)["total"], 1)

    def test_25_same_type_set_with_different_counts_does_not_false_cluster(self):
        left = self.blueprint(["main_title", "product_image", "selling_point"])
        right = self.blueprint([
            "main_title", "main_title", "product_image", "product_image",
            "selling_point", "selling_point", "selling_point",
        ])
        self.assertLess(structure_similarity(left, right)["total"], .72)

    def test_26_unverified_cases_are_explicit_supplements_only(self):
        normal_ids = {row["id"] for row in self.search()["cases"]}
        supplement = self.search(include_unverified=True)
        supplement_row = next(
            row for row in supplement["cases"]
            if row["id"] == self.unverified_case_id
        )
        self.assertNotIn(self.unverified_case_id, normal_ids)
        self.assertEqual(supplement_row["review_status"], "ai_generated")
        self.assertIn("未确认补充结果", supplement_row["match_reasons"])

    def test_27_changed_algorithm_warns_about_historical_patterns(self):
        candidates = discover_candidates(self.db)
        warned = [row for row in candidates if row["historical_pattern_ids"]]
        self.assertTrue(warned)
        self.assertTrue(warned[0]["warnings"])

    def test_28_ground_truth_list_api(self):
        response = self.client.get(
            "/api/layout-search/ground-truth?dataset_version=fixture-predefined-v1"
        )
        self.assertEqual(len(response.json()), 125)

    def test_29_frozen_ground_truth_is_immutable(self):
        response = self.client.post("/api/layout-search/ground-truth", json={
            "requirement_id": self.requirement_ids[0], "result_type": "case",
            "result_id": self.case_ids[0][0], "expected_relevance": "relevant",
            "reviewer": "late", "reason": "", "dataset_version": "fixture-predefined-v1",
            "dataset_split": "calibration",
        })
        self.assertEqual(response.status_code, 400)

    def test_30_empty_dataset_cannot_freeze(self):
        response = self.client.post(
            "/api/layout-search/ground-truth/freeze",
            json={"dataset_version": "empty-v1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_31_run_requires_frozen_ground_truth(self):
        response = self.client.post(
            "/api/layout-search/evaluation/run",
            json={"dataset_version": "empty-v1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_32_evaluation_separates_splits(self):
        report = evaluation(self.db, "fixture-predefined-v1")
        self.assertEqual(report["calibration"]["metrics"]["requirement_count"], 3)
        self.assertEqual(report["holdout"]["metrics"]["requirement_count"], 2)

    def test_33_evaluation_has_direct_case_metric(self):
        self.assertIn(
            "case_direct_precision_at_5",
            evaluation(self.db, "fixture-predefined-v1")["overall"]["metrics"],
        )

    def test_34_evaluation_has_useful_case_metric(self):
        self.assertIn(
            "case_useful_precision_at_10",
            evaluation(self.db, "fixture-predefined-v1")["overall"]["metrics"],
        )

    def test_35_evaluation_has_case_recall(self):
        self.assertIn(
            "case_recall_at_10",
            evaluation(self.db, "fixture-predefined-v1")["overall"]["metrics"],
        )

    def test_36_evaluation_has_pattern_metrics(self):
        metrics = evaluation(self.db, "fixture-predefined-v1")["overall"]["metrics"]
        self.assertIn("pattern_direct_precision_at_3", metrics)
        self.assertIn("pattern_useful_precision_at_5", metrics)

    def test_37_evaluation_reports_false_positives_and_negatives(self):
        row = evaluation(
            self.db, "fixture-predefined-v1"
        )["overall"]["requirements"][0]
        self.assertIn("false_positives", row)
        self.assertIn("false_negatives", row)

    def test_38_evaluation_reports_traceability(self):
        metrics = evaluation(self.db, "fixture-predefined-v1")["overall"]["metrics"]
        self.assertEqual(metrics["traceability_rate"], 1)

    def test_39_unknown_dataset_is_not_ready(self):
        report = evaluation(self.db, "missing-v1")
        self.assertEqual(report["status"], "not_ready")
        self.assertEqual(report["message"], "尚未完成真实业务验收")

    def test_40_business_alias_is_exact_and_explained(self):
        self.assertEqual(normalize_business_value("channel", "RED"), "小红书")

    def test_41_unmatched_business_value_is_preserved(self):
        self.assertEqual(
            normalize_business_value("channel", "自建新品频道"), "自建新品频道"
        )

    def test_42_business_match_does_not_use_contains(self):
        self.assertFalse(values_match("channel", "小红书专题页", "小红书"))

    def test_43_reference_cache_has_content_identity(self):
        result = self.search()
        meta = result["search_summary"]["reference_analysis"]
        self.assertIn("image_sha256", meta)
        self.assertEqual(meta["analyzer_version"], "reference-layout-v2")
