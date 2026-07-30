"""检索评测脚手架的回归守护。

用自建种子库验证：指标计算正确，且已知相关的模式/案例被检索到 top-K。
后续改检索逻辑若让已知相关项掉出 top-K，本测试会报警。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-eval-test-")
_root = Path(_tmp.name)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_root / 'unused.db'}")
os.environ.setdefault("UPLOAD_DIR", str(_root / "uploads"))
os.environ.setdefault("VISION_PROVIDER", "mock")

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from evaluation import harness, metrics  # noqa: E402

# 用独立引擎，绝不复用应用共享的 SessionLocal——本套件在模块导入期绑定引擎，
# 若写进共享库会污染其它测试。这里的种子只落在自己的临时库里。
_engine = create_engine(
    f"sqlite:///{_root / 'eval.db'}",
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


class MetricsUnitTest(unittest.TestCase):
    def test_recall_mrr_ndcg(self):
        self.assertEqual(metrics.recall_at_k([1, 2, 3], [3, 9], 3), 0.5)
        self.assertEqual(metrics.mrr([9, 3, 1], [3]), 0.5)
        self.assertIsNone(metrics.recall_at_k([1, 2], [], 3))
        # 完美排序 nDCG = 1.0
        self.assertAlmostEqual(metrics.ndcg_at_k([1, 2], {1: 2, 2: 1}, 3), 1.0)
        # 相关项排在后面，nDCG < 1
        self.assertLess(metrics.ndcg_at_k([9, 1], {1: 1}, 3), 1.0)


class HarnessEvalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with _Session() as db:
            cls.match_pattern_id = cls._seed(db)

    @staticmethod
    def _seed(db) -> int:
        def pattern(name, orientation, ratio, industry, channel, status="verified"):
            row = models.LayoutPattern(
                name=name,
                orientation=orientation,
                canvas_ratio=ratio,
                information_density="medium",
                modules_json="[]",
                source_case_ids="[]",
                industry_tags=json.dumps([industry], ensure_ascii=False),
                channel_tags=json.dumps([channel], ensure_ascii=False),
                scene_tags="[]",
                business_goal_tags="[]",
                review_status=status,
                editor="seed",
            )
            db.add(row)
            db.flush()
            return row

        def case_with_blueprint(name, industry, channel, orientation):
            image = models.Image(url=f"/uploads/{name}.png", filename=f"{name}.png")
            db.add(image)
            db.flush()
            case = models.Case(
                image_id=image.id,
                name=name,
                industry=industry,
                channel=channel,
            )
            db.add(case)
            db.flush()
            db.add(
                models.LayoutBlueprint(
                    case_id=case.id,
                    canvas_ratio="2:3",
                    orientation=orientation,
                    module_count=0,
                    modules_json="[]",
                    review_status="verified",
                    version=1,
                )
            )
            return case

        match_pattern = pattern("竖版母婴小红书", "portrait", "2:3", "母婴", "小红书")
        pattern("横版数码电商", "landscape", "16:9", "数码", "电商详情")
        match_case = case_with_blueprint("母婴案例", "母婴", "小红书", "portrait")
        case_with_blueprint("数码案例", "数码", "电商详情", "landscape")
        db.commit()
        HarnessEvalTest.match_case_id = match_case.id
        return match_pattern.id

    def _eval_items(self):
        return [
            {
                "id": "t1",
                "title": "吸奶器新品小红书",
                "requirement": {
                    "industry": "母婴",
                    "channel": "小红书",
                    "orientation": "portrait",
                    "canvas_ratio": "2:3",
                    "information_density": "medium",
                    "request_text": "母婴新品种草",
                },
                "relevant": {
                    "patterns": [self.match_pattern_id],
                    "cases": [self.match_case_id],
                },
            }
        ]

    def test_relevant_items_rank_top_and_metrics_compute(self):
        with _Session() as db:
            result = harness.evaluate(db, self._eval_items(), k_values=(3, 5))
        patterns = result["aggregate"]["patterns"]
        cases = result["aggregate"]["cases"]
        # 已知相关的模式/案例应在 top-3 命中
        self.assertEqual(patterns["recall@3"], 1.0)
        self.assertEqual(cases["recall@3"], 1.0)
        # 更贴合需求的模式/案例应排在第一位
        self.assertEqual(patterns["mrr"], 1.0)
        self.assertEqual(cases["mrr"], 1.0)
        self.assertEqual(patterns["evaluated"], 1)

    def test_empty_gold_is_skipped(self):
        items = [{"id": "t2", "requirement": {"industry": "母婴"}, "relevant": {}}]
        with _Session() as db:
            result = harness.evaluate(db, items, k_values=(3,))
        # 无金标准 → 不计入聚合
        self.assertEqual(result["aggregate"]["patterns"]["evaluated"], 0)
        self.assertIsNone(result["aggregate"]["patterns"]["recall@3"])


if __name__ == "__main__":
    unittest.main()
