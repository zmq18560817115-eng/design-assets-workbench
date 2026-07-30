"""拆解保真度分析的回归守护。

用手工模块对验证编辑分类，用自建种子库验证抽取与分层聚合。
测试使用独立引擎，绝不复用套件共享的 SessionLocal，种子不会泄漏到其它测试。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-fidelity-test-")
_root = Path(_tmp.name)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_root / 'unused.db'}")
os.environ.setdefault("UPLOAD_DIR", str(_root / "uploads"))
os.environ.setdefault("VISION_PROVIDER", "mock")

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from evaluation import blueprint_fidelity as bf  # noqa: E402

_engine = create_engine(
    f"sqlite:///{_root / 'fidelity.db'}",
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


def _mod(mid, mtype, x, y, w, h):
    return {"id": mid, "type": mtype, "x": x, "y": y, "width": w, "height": h}


# v1：模板兜底，用了非规范类型 title / supporting_text
V1 = [
    _mod("m1", "title", 0.08, 0.05, 0.84, 0.12),
    _mod("m2", "supporting_text", 0.10, 0.70, 0.80, 0.12),
    _mod("m3", "product_image", 0.12, 0.22, 0.76, 0.44),
    _mod("m4", "cta", 0.30, 0.87, 0.40, 0.07),
]
# 人工终版：类型规范化 + 主视觉微移 + 新增 price
V2 = [
    _mod("a", "main_title", 0.08, 0.05, 0.84, 0.12),
    _mod("b", "body_text", 0.10, 0.70, 0.80, 0.12),
    _mod("c", "product_image", 0.12, 0.24, 0.76, 0.44),
    _mod("d", "cta", 0.30, 0.87, 0.40, 0.07),
    _mod("e", "price", 0.10, 0.58, 0.30, 0.08),
]


class AnalyzePairTest(unittest.TestCase):
    def test_iou(self):
        self.assertAlmostEqual(bf._iou(V1[0], V2[0]), 1.0)
        self.assertEqual(bf._iou(V1[0], V2[4]), 0.0)

    def test_edit_classification(self):
        stats = bf.analyze_pair(V1, V2)
        self.assertEqual(stats["matched"], 4)
        self.assertEqual(stats["retyped"], 2)      # title→main_title, supporting_text→body_text
        self.assertEqual(stats["same_type"], 2)    # product_image, cta
        self.assertEqual(stats["added"], 1)        # price
        self.assertEqual(stats["dropped"], 0)
        self.assertEqual(stats["noncanonical_x"], 2)
        self.assertAlmostEqual(stats["edit_rate"], 3 / 5)

    def test_gen_path(self):
        self.assertEqual(bf.gen_path("template-fallback+heuristic"), "template")
        self.assertEqual(bf.gen_path("region-detection-fallback+x"), "region")
        self.assertEqual(bf.gen_path("doubao-vision"), "model")


class ExtractAndAnalyzeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with _Session() as db:
            image = models.Image(url="/uploads/f.png", filename="f.png")
            db.add(image)
            db.flush()
            case = models.Case(image_id=image.id, name="保真度案例")
            db.add(case)
            db.flush()
            db.add(
                models.LayoutBlueprint(
                    case_id=case.id, orientation="portrait", canvas_ratio="2:3",
                    module_count=len(V1), modules_json=json.dumps(V1),
                    review_status="ai_generated",
                    model_name="template-fallback+heuristic", version=1,
                )
            )
            db.add(
                models.LayoutBlueprint(
                    case_id=case.id, orientation="portrait", canvas_ratio="2:3",
                    module_count=len(V2), modules_json=json.dumps(V2),
                    review_status="verified", model_name="human", version=2,
                )
            )
            db.commit()

    def test_extract_and_stratify(self):
        with _Session() as db:
            result = bf.analyze(db)
        self.assertEqual(result["pair_count"], 1)
        self.assertIn("template", result["by_gen_path"])
        self.assertIn("portrait", result["by_orientation"])
        overall = result["overall"]
        self.assertEqual(overall["type_accuracy"], 0.5)       # 2/4 matched same type
        self.assertEqual(overall["noncanonical_x_rate"], 0.5)  # 2/4 v1 modules
        self.assertGreater(overall["mean_edit_rate"], 0.0)

    def test_report_renders(self):
        with _Session() as db:
            report = bf.format_report(bf.analyze(db))
        self.assertIn("拆解保真度报告", report)
        self.assertIn("gen_path", report)


if __name__ == "__main__":
    unittest.main()
