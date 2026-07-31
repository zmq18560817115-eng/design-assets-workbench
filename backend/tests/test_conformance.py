"""L2 结构符合度逻辑守护（纯函数，用 stub 模式，无需 DB / 图片）。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/unused.db")

from app import conformance  # noqa: E402

_WORK_MODULES = [
    {"type": "main_title", "x": 0.1, "y": 0.05, "width": 0.8, "height": 0.12},
    {"type": "product_image", "x": 0.1, "y": 0.25, "width": 0.8, "height": 0.5},
]


def _work():
    return {
        "modules_json": _WORK_MODULES,
        "grid_columns": 6,
        "grid_rows": 12,
        "reading_flow": "top-to-bottom",
        "layout_signature": "",
        "orientation": "portrait",
        "canvas_ratio": "2:3",
        "information_density": "medium",
    }


def _pattern(pattern_id, name, modules, *, orientation, canvas, density, grid=(6, 12)):
    return SimpleNamespace(
        id=pattern_id,
        name=name,
        pattern_code=f"P{pattern_id}",
        average_positions_json=json.dumps(modules, ensure_ascii=False),
        modules_json=json.dumps(modules, ensure_ascii=False),
        grid_columns=grid[0],
        grid_rows=grid[1],
        reading_flow="top-to-bottom",
        layout_signature="",
        orientation=orientation,
        canvas_ratio=canvas,
        information_density=density,
    )


class ConformanceTest(unittest.TestCase):
    def test_na_when_no_patterns(self):
        report = conformance.evaluate_conformance(_work(), [])
        self.assertEqual(report["verdict"], "na")
        self.assertFalse(report["conforms"])

    def test_conforms_to_matching_pattern(self):
        same = _pattern(1, "竖版标题主视觉", _WORK_MODULES,
                        orientation="portrait", canvas="2:3", density="medium")
        different = _pattern(2, "横向参数表", [
            {"type": "parameter_table", "x": 0.0, "y": 0.0, "width": 0.3, "height": 0.3}
        ], orientation="landscape", canvas="16:9", density="high", grid=(1, 1))
        report = conformance.evaluate_conformance(_work(), [different, same])
        self.assertEqual(report["verdict"], "conforms")
        self.assertTrue(report["conforms"])
        self.assertEqual(report["best"]["pattern_id"], 1)
        self.assertGreaterEqual(report["best"]["similarity"], report["threshold"])

    def test_deviates_when_only_dissimilar(self):
        different = _pattern(2, "横向参数表", [
            {"type": "parameter_table", "x": 0.0, "y": 0.0, "width": 0.3, "height": 0.3}
        ], orientation="landscape", canvas="16:9", density="high", grid=(1, 1))
        report = conformance.evaluate_conformance(_work(), [different])
        self.assertEqual(report["verdict"], "deviates")
        self.assertFalse(report["conforms"])
        self.assertEqual(report["best"]["pattern_id"], 2)


if __name__ == "__main__":
    unittest.main()
