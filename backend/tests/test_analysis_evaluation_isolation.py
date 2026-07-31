from __future__ import annotations

import unittest
import json
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import analysis_evaluation, models
from app.database import Base


class AnalysisEvaluationIsolationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        image = models.Image(url="/uploads/a.png", filename="a.png")
        self.db.add(image)
        self.db.flush()
        self.case = models.Case(image_id=image.id, name="sample")
        self.db.add(self.case)
        self.db.commit()
        self.dataset = analysis_evaluation.create_dataset(
            self.db,
            {
                "dataset_version": "visual-v1",
                "name": "Visual V1",
                "product_category": "消毒柜",
                "description": "",
                "created_by": "负责人",
            },
        )

    def tearDown(self):
        self.db.close()

    def test_case_cannot_cross_calibration_and_holdout(self):
        analysis_evaluation.assign_item(
            self.db,
            self.dataset,
            {
                "case_id": self.case.id,
                "dataset_split": "calibration",
                "reviewer": "",
                "reason": "",
            },
        )
        with self.assertRaisesRegex(
            analysis_evaluation.EvaluationConflict, "不能同时属于"
        ):
            analysis_evaluation.assign_item(
                self.db,
                self.dataset,
                {
                    "case_id": self.case.id,
                    "dataset_split": "holdout",
                    "reviewer": "",
                    "reason": "",
                },
            )

    def test_designer_summary_never_exposes_holdout_ground_truth(self):
        item = analysis_evaluation.assign_item(
            self.db,
            self.dataset,
            {
                "case_id": self.case.id,
                "dataset_split": "holdout",
                "reviewer": "",
                "reason": "",
            },
        )
        item.ground_truth_json = '{"secret":"answer"}'
        item.gt_status = "ready"
        self.db.commit()
        detail = analysis_evaluation.dataset_detail(
            self.db, self.dataset, admin=False
        )
        self.assertEqual(detail["counts"]["holdout"], 1)
        self.assertEqual(detail["items"], [])
        self.assertNotIn("secret", str(detail))

    def test_runtime_versions_are_append_only(self):
        payload = {
            "model_name": "vision-model",
            "model_provider": "volcengine",
            "prompt_version": "prompt-v1",
            "prompt_text": "analyze",
            "validator_version": "validator-v1",
            "validator_config": {"overlap": 0.2},
            "created_by": "负责人",
        }
        first = analysis_evaluation.create_runtime(self.db, dict(payload))
        payload["prompt_version"] = "prompt-v2"
        second = analysis_evaluation.create_runtime(self.db, dict(payload))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.prompt_version, "prompt-v1")

    def _ready_item(self, case, split):
        item = analysis_evaluation.assign_item(
            self.db, self.dataset, {
                "case_id": case.id, "dataset_split": split,
                "reviewer": "负责人", "reason": "固定前建立 GT",
            }
        )
        item.gt_status = "ready"
        item.ground_truth_json = json.dumps({
            "has_product": True, "allowed_overlaps": [],
        })
        self.db.commit()
        return item

    def _blueprint(self, case, modules):
        row = models.LayoutBlueprint(
            case_id=case.id, orientation="portrait", version=1,
            model_name="vision-model", prompt_version="prompt-v1",
            modules_json=json.dumps(modules), module_count=len(modules),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def _runtime(self):
        return analysis_evaluation.create_runtime(self.db, {
            "model_name": "vision-model", "model_provider": "volcengine",
            "prompt_version": "prompt-v1", "prompt_text": "analyze",
            "validator_version": "validator-v1",
            "validator_config": {"minimum_pass_rate": 0.8, "maximum_overlap_ratio": 0.85},
            "created_by": "负责人",
        })

    def test_holdout_requires_frozen_calibration_and_is_single_use(self):
        calibration_case = self.case
        holdout_image = models.Image(url="/uploads/b.png", filename="b.png")
        self.db.add(holdout_image)
        self.db.flush()
        holdout_case = models.Case(image_id=holdout_image.id, name="holdout")
        self.db.add(holdout_case)
        self.db.commit()
        self._ready_item(calibration_case, "calibration")
        self._ready_item(holdout_case, "holdout")
        module = {
            "id": "product", "type": "product_image",
            "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.5,
        }
        self._blueprint(calibration_case, [module])
        self._blueprint(holdout_case, [module])
        self.dataset.status = "gt_ready"
        self.db.commit()
        runtime = self._runtime()
        with self.assertRaisesRegex(
            analysis_evaluation.EvaluationConflict, "未冻结"
        ):
            analysis_evaluation.run_evaluation(
                self.db, self.dataset, runtime, dataset_split="holdout",
                actor="负责人", confirm_holdout=True,
            )
        calibration = analysis_evaluation.run_evaluation(
            self.db, self.dataset, runtime, dataset_split="calibration",
            actor="负责人", confirm_holdout=False,
        )
        self.assertEqual(calibration.run_status, "passed")
        analysis_evaluation.freeze_runtime(self.db, self.dataset, runtime)
        holdout = analysis_evaluation.run_evaluation(
            self.db, self.dataset, runtime, dataset_split="holdout",
            actor="负责人", confirm_holdout=True,
        )
        sealed = analysis_evaluation.run_to_dict(
            holdout, include_details=False, db=self.db
        )
        self.assertNotIn("results", sealed)
        with self.assertRaises(analysis_evaluation.EvaluationConflict):
            analysis_evaluation.run_evaluation(
                self.db, self.dataset, runtime, dataset_split="holdout",
                actor="负责人", confirm_holdout=True,
            )
        analysis_evaluation.mark_consumed(self.dataset)
        self.db.commit()
        with self.assertRaisesRegex(
            analysis_evaluation.EvaluationConflict, "consumed"
        ):
            analysis_evaluation.run_evaluation(
                self.db, self.dataset, runtime, dataset_split="holdout",
                actor="负责人", confirm_holdout=True,
            )

    def test_overlap_has_explicit_error_code(self):
        self._ready_item(self.case, "calibration")
        self._blueprint(self.case, [
            {"id": "product", "type": "product_image", "x": 0.1, "y": 0.1, "width": 0.6, "height": 0.6},
            {"id": "title", "type": "main_title", "x": 0.1, "y": 0.1, "width": 0.6, "height": 0.6},
        ])
        outcome = analysis_evaluation.evaluate_item(
            self.db,
            self.db.query(models.AnalysisEvaluationItem).first(),
            {"maximum_overlap_ratio": 0.8},
        )
        self.assertEqual(outcome["error_code"], "MODULE_OVERLAP")

    def test_product_missed_enters_calibration_diagnostic(self):
        self._ready_item(self.case, "calibration")
        self._blueprint(self.case, [{
            "id": "title", "type": "main_title",
            "x": 0.1, "y": 0.1, "width": 0.6, "height": 0.2,
        }])
        outcome = analysis_evaluation.evaluate_item(
            self.db,
            self.db.query(models.AnalysisEvaluationItem).first(),
            {},
        )
        self.assertEqual(outcome["error_code"], "PRODUCT_MISSED")

    def test_sealed_holdout_hides_item_identity_even_from_admin_summary(self):
        self._ready_item(self.case, "holdout")
        self.dataset.sealed_at = dt.datetime.utcnow()
        self.dataset.status = "holdout_ready"
        self.db.commit()
        detail = analysis_evaluation.dataset_detail(
            self.db, self.dataset, admin=True
        )
        self.assertEqual(detail["counts"]["holdout"], 1)
        self.assertEqual(detail["items"], [])

    def test_timeout_result_can_be_retried_individually_in_calibration(self):
        item = self._ready_item(self.case, "calibration")
        self._blueprint(self.case, [{
            "id": "product", "type": "product_image",
            "x": 0.1, "y": 0.1, "width": 0.6, "height": 0.6,
        }])
        runtime = self._runtime()
        run = models.AnalysisEvaluationRun(
            dataset_id=self.dataset.id, dataset_split="calibration",
            runtime_version_id=runtime.id, formal=False,
            run_status="failed", created_by="负责人",
        )
        self.db.add(run)
        self.db.flush()
        result = models.AnalysisEvaluationResult(
            run_id=run.id, item_id=item.id, status="failed",
            error_code="MODEL_TIMEOUT",
        )
        self.db.add(result)
        self.db.commit()
        retried = analysis_evaluation.retry_result(
            self.db, result, actor="负责人"
        )
        self.assertEqual(retried["status"], "passed")
        self.assertEqual(retried["error_code"], "")


if __name__ == "__main__":
    unittest.main()
