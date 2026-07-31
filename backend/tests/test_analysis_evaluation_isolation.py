from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
