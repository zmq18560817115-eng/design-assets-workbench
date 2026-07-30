"""批量导入进度持久化与重启恢复的守护。

用隔离引擎 + monkeypatch batch.SessionLocal，避免写进套件共享库。
用"不存在的图"作为条目，拆解必失败 → 不产生案例 → 不污染其它测试。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-batch-test-")
_root = Path(_tmp.name)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_root / 'unused.db'}")
os.environ.setdefault("UPLOAD_DIR", str(_root / "uploads"))
os.environ.setdefault("VISION_PROVIDER", "mock")

from app import batch, models  # noqa: E402
from app.database import Base  # noqa: E402

_engine = create_engine(
    f"sqlite:///{_root / 'batch.db'}",
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


class BatchPersistenceTest(unittest.TestCase):
    def setUp(self):
        self._orig_session = batch.SessionLocal
        batch.SessionLocal = _Session

    def tearDown(self):
        batch.SessionLocal = self._orig_session

    def test_unknown_batch_returns_none(self):
        self.assertIsNone(batch.get_batch("does-not-exist"))

    def test_run_persists_progress_and_completes(self):
        with _Session() as db:
            db.add(models.BatchImportJob(id="b1", status="processing", total=2, concurrency=1))
            db.commit()
        items = [
            {"path": "/no/such/a.png", "url": "/uploads/a.png", "filename": "a.png"},
            {"path": "/no/such/b.png", "url": "/uploads/b.png", "filename": "b.png"},
        ]
        batch._run("b1", items)
        got = batch.get_batch("b1")
        self.assertEqual(got["status"], "completed")
        self.assertEqual(got["failed"], 2)
        self.assertEqual(got["done"], 0)
        self.assertEqual(got["case_ids"], [])
        self.assertEqual(len(got["errors"]), 2)
        self.assertIsNotNone(got["finished_at"])

    def test_recover_stale_marks_interrupted(self):
        with _Session() as db:
            db.add(models.BatchImportJob(id="b2", status="processing", total=5))
            db.commit()
        with _Session() as db:
            recovered = batch.recover_stale_jobs(db)
            db.commit()
        self.assertGreaterEqual(recovered, 1)
        got = batch.get_batch("b2")
        self.assertEqual(got["status"], "interrupted")
        self.assertTrue(got["errors"])


if __name__ == "__main__":
    unittest.main()
