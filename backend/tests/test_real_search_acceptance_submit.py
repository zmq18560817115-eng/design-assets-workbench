import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, real_search_acceptance
from app.database import Base


class RealSearchAcceptanceSubmitTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        dataset = models.LayoutSearchDataset(
            dataset_version=real_search_acceptance.DATASET_VERSION,
            name="真实验收", created_by="张茗淇",
        )
        self.db.add(dataset)
        self.db.flush()
        for requirement_id in real_search_acceptance.CALIBRATION_IDS:
            self.db.add(models.BusinessRequirement(
                id=requirement_id, title=f"需求{requirement_id}", raw_requirement="真实Brief",
            ))
            run = models.LayoutSearchRun(
                requirement_id=requirement_id, query_snapshot_json="{}",
                result_snapshot_json=json.dumps({"cases": [], "patterns": []}),
            )
            self.db.add(run)
            self.db.flush()
            self.db.add(models.LayoutSearchDatasetRequirement(
                dataset_id=dataset.id, requirement_id=requirement_id,
                dataset_split="calibration", search_run_id=run.id,
            ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_complete_submit_is_atomic_and_idempotent(self):
        decisions = [{
            "requirement_id": requirement_id, "result_type": "none", "result_id": 0,
            "relevance": "relevant", "reasons": ["当前没有合适结果"], "notes": "",
        } for requirement_id in real_search_acceptance.CALIBRATION_IDS]
        with self.assertRaises(real_search_acceptance.AcceptancePreparationError):
            real_search_acceptance.submit_ground_truth(
                self.db, real_search_acceptance.DATASET_VERSION,
                reviewer="张茗淇", decisions=decisions[:-1],
            )
        self.assertEqual(self.db.query(models.LayoutSearchGroundTruth).count(), 0)
        first = real_search_acceptance.submit_ground_truth(
            self.db, real_search_acceptance.DATASET_VERSION,
            reviewer="张茗淇", decisions=decisions,
        )
        second = real_search_acceptance.submit_ground_truth(
            self.db, real_search_acceptance.DATASET_VERSION,
            reviewer="张茗淇", decisions=decisions,
        )
        self.assertEqual(first["created"], 7)
        self.assertEqual(second["created"], 0)
        self.assertEqual(self.db.query(models.LayoutSearchGroundTruth).count(), 7)


if __name__ == "__main__":
    unittest.main()
