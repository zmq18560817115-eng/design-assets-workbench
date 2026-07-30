"""守护 VLM 蓝图提示词与规范模块类型词表一致。

拆解初版质量的关键杠杆之一：视觉模型必须清楚它只能输出哪些模块类型，否则会吐出
越界类型、被 validate_modules 拒绝、退回更粗糙的启发式路径，加重人工校正。
提示词里的类型枚举必须始终覆盖 MODULE_TYPE_ORDER。
"""
from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/unused.db")
os.environ.setdefault("VISION_PROVIDER", "mock")

from app import vlm  # noqa: E402
from app.layout_blueprint import MODULE_TYPE_ORDER, MODULE_TYPES  # noqa: E402


class VlmPromptTest(unittest.TestCase):
    def test_type_order_matches_set(self):
        self.assertEqual(set(MODULE_TYPE_ORDER), MODULE_TYPES)
        self.assertEqual(len(MODULE_TYPE_ORDER), len(MODULE_TYPES))  # 无重复

    def test_prompt_enumerates_every_canonical_type(self):
        text = vlm.USER_TEMPLATE.format(
            palette="", tone="", grid_columns="", modules="", margins="",
            module_types=", ".join(MODULE_TYPE_ORDER),
        )
        for module_type in MODULE_TYPE_ORDER:
            self.assertIn(module_type, text)
        # 旧的含糊表述已移除
        self.assertNotIn("只能使用约定类型", text)


if __name__ == "__main__":
    unittest.main()
