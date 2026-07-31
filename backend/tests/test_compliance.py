"""L1 合规判定逻辑守护（纯函数，无需 DB / 图片 / 模型）。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/unused.db")

from app import compliance  # noqa: E402


def _req(required=None, forbidden=None, canvas="", orientation="", density=""):
    return SimpleNamespace(
        required_modules_json=json.dumps(required or []),
        forbidden_modules_json=json.dumps(forbidden or []),
        canvas_ratio=canvas,
        orientation=orientation,
        information_density=density,
    )


def _work(types, canvas="2:3", orientation="portrait", density="medium"):
    return {
        "canvas_ratio": canvas,
        "orientation": orientation,
        "information_density": density,
        "modules_json": [
            {"type": t, "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1} for t in types
        ],
    }


class ComplianceTest(unittest.TestCase):
    def test_pass_when_required_present_and_structure_matches(self):
        req = _req(
            required=["main_title", "product_image"],
            forbidden=["parameter_table"],
            canvas="2:3", orientation="portrait", density="medium",
        )
        rep = compliance.evaluate_compliance(
            _work(["main_title", "product_image", "cta"]), req
        )
        self.assertEqual(rep["verdict"], "pass")
        self.assertTrue(rep["compliant"])
        self.assertEqual(rep["missing_required"], [])
        self.assertEqual(rep["forbidden_present"], [])

    def test_fail_on_missing_required(self):
        req = _req(required=["main_title", "selling_point"])
        rep = compliance.evaluate_compliance(_work(["main_title", "product_image"]), req)
        self.assertEqual(rep["verdict"], "fail")
        self.assertFalse(rep["compliant"])
        self.assertIn("selling_point", rep["missing_required"])

    def test_fail_on_forbidden_present(self):
        req = _req(forbidden=["parameter_table"])
        rep = compliance.evaluate_compliance(_work(["main_title", "parameter_table"]), req)
        self.assertEqual(rep["verdict"], "fail")
        self.assertFalse(rep["compliant"])
        self.assertIn("parameter_table", rep["forbidden_present"])

    def test_warn_on_canvas_mismatch_but_hard_compliant(self):
        req = _req(required=["main_title"], canvas="1:1", orientation="square")
        rep = compliance.evaluate_compliance(
            _work(["main_title"], canvas="2:3", orientation="portrait"), req
        )
        self.assertEqual(rep["verdict"], "warn")
        self.assertTrue(rep["compliant"])  # 硬性合规仍通过
        dims = {c["dimension"]: c["status"] for c in rep["checks"]}
        self.assertEqual(dims["canvas_ratio"], "warn")
        self.assertEqual(dims["orientation"], "warn")

    def test_na_when_requirement_unspecified(self):
        rep = compliance.evaluate_compliance(_work(["main_title"]), _req())
        self.assertEqual(rep["verdict"], "pass")
        dims = {c["dimension"]: c["status"] for c in rep["checks"]}
        self.assertEqual(dims["canvas_ratio"], "na")
        self.assertEqual(dims["information_density"], "na")


if __name__ == "__main__":
    unittest.main()
