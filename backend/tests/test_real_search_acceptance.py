import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, real_search_acceptance
from app.database import Base


class RealSearchAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        for requirement_id in range(1, 11):
            self.db.add(models.BusinessRequirement(
                id=requirement_id,
                title=f"真实需求 {requirement_id}",
                raw_requirement="真实Brief",
                status="confirmed",
                product_category="消毒柜" if requirement_id in {1, 5, 6, 7} else "恒温杯",
                content_purpose="评测",
                page_role="评测页",
            ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def gates():
        return {
            "gates": {
                "confirmed_requirements_exactly_10": True,
                "verified_case_contexts_at_least_50": True,
                "searchable_company_cases_at_least_50": True,
                "verified_formal_patterns_at_least_5": True,
            },
            "confirmed_requirement_count": 10,
            "verified_case_context_count": 50,
            "searchable_company_case_count": 50,
            "verified_formal_pattern_count": 6,
            "searchable_case_ids": list(range(1, 51)),
        }

    def fake_search(self, db, requirement, **kwargs):
        self.assertTrue(kwargs["strict_product_category"])
        self.assertEqual(kwargs["pattern_limit"], 3)
        self.assertEqual(kwargs["case_limit"], 10)
        run = models.LayoutSearchRun(
            requirement_id=requirement.id,
            query_snapshot_json="{}",
            result_snapshot_json=json.dumps({"cases": [], "patterns": []}),
        )
        db.add(run)
        db.flush()
        return {"search_run_id": run.id}

    def test_fixed_split_runs_only_calibration_and_hides_holdout_identity(self):
        with patch.object(real_search_acceptance, "prerequisites", return_value=self.gates()), patch.object(real_search_acceptance.layout_search, "run_search", side_effect=self.fake_search) as search:
            result = real_search_acceptance.prepare(self.db)
        self.assertEqual(search.call_count, 7)
        self.assertEqual(result["calibration_count"], 7)
        self.assertEqual(result["holdout_count"], 3)
        self.assertFalse(result["holdout_executed"])
        self.assertFalse(result["holdout_read"])
        self.assertNotIn("holdout_requirement_ids", result)
        self.assertEqual(self.db.query(models.LayoutSearchRun).count(), 7)
        self.assertEqual(self.db.query(models.LayoutSearchGroundTruth).count(), 0)

    def test_repeated_prepare_creates_no_new_dataset_or_run(self):
        with patch.object(real_search_acceptance, "prerequisites", return_value=self.gates()), patch.object(real_search_acceptance.layout_search, "run_search", side_effect=self.fake_search):
            real_search_acceptance.prepare(self.db)
            run_count = self.db.query(models.LayoutSearchRun).count()
            real_search_acceptance.prepare(self.db)
        self.assertEqual(self.db.query(models.LayoutSearchDataset).count(), 1)
        self.assertEqual(self.db.query(models.LayoutSearchRun).count(), run_count)

    def test_judgment_requires_reviewer_and_calibration_membership(self):
        with patch.object(real_search_acceptance, "prerequisites", return_value=self.gates()), patch.object(real_search_acceptance.layout_search, "run_search", side_effect=self.fake_search):
            real_search_acceptance.prepare(self.db)
        with self.assertRaises(real_search_acceptance.AcceptancePreparationError):
            real_search_acceptance.add_judgment(
                self.db, real_search_acceptance.DATASET_VERSION,
                requirement_id=1, result_type="none", result_id=0,
                relevance="relevant", reviewer="",
            )
        with self.assertRaises(real_search_acceptance.AcceptancePreparationError):
            real_search_acceptance.add_judgment(
                self.db, real_search_acceptance.DATASET_VERSION,
                requirement_id=2, result_type="none", result_id=0,
                relevance="relevant", reviewer="张茗淇",
            )
