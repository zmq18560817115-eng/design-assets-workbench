"""守护 _direction_modules 的策略变换。

历史上这些分支按已废弃的 "supporting_text" 类型匹配，而蓝图/模式在存储层已被
规范化为 "body_text"，导致 balanced/exploratory 变换成为死代码。对齐到规范类型
后，本测试确保变换真正生效。
"""
from __future__ import annotations

import os
import tempfile
import unittest

_root = tempfile.mkdtemp(prefix="design-assets-dir-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_root}/unused.db")
os.environ.setdefault("UPLOAD_DIR", f"{_root}/uploads")
os.environ.setdefault("VISION_PROVIDER", "mock")

from app import crud  # noqa: E402


def _base():
    return [
        {"id": "m1", "type": "main_title", "x": 0.10, "y": 0.05, "width": 0.80, "height": 0.12},
        {"id": "m2", "type": "product_image", "x": 0.10, "y": 0.22, "width": 0.80, "height": 0.40},
        {"id": "m3", "type": "body_text", "x": 0.10, "y": 0.66, "width": 0.80, "height": 0.12},
    ]


class DirectionModulesTest(unittest.TestCase):
    def test_conservative_is_unchanged(self):
        out = crud._direction_modules(_base(), "conservative")
        self.assertEqual([m["type"] for m in out], ["main_title", "product_image", "body_text"])
        self.assertEqual(len(out), 3)

    def test_balanced_enhances_visual_and_body(self):
        out = crud._direction_modules(_base(), "balanced")
        by_type = {m["type"]: m for m in out}
        # 主视觉被加宽
        self.assertGreater(by_type["product_image"]["width"], 0.80)
        # body_text 被增高（此前的死分支，现应生效）
        self.assertGreater(by_type["body_text"]["height"], 0.12)

    def test_exploratory_splits_body_text(self):
        out = crud._direction_modules(_base(), "exploratory")
        ids = {m["id"] for m in out}
        self.assertIn("m3-a", ids)
        self.assertIn("m3-b", ids)
        self.assertEqual(len(out), 4)


if __name__ == "__main__":
    unittest.main()
