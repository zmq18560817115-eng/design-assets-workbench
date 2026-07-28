"""第一阶段主链路冒烟测试。

运行：
    cd backend
    python -m unittest tests.test_phase1_flow -v
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-test-")
_root = Path(_tmp.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_root / "uploads")
os.environ["VISION_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def sample_image(color: str, accent: str, *, vertical: bool = True) -> bytes:
    size = (720, 1080) if vertical else (1080, 720)
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (size[0] * 0.1, size[1] * 0.12, size[0] * 0.9, size[1] * 0.42),
        radius=30,
        fill=accent,
    )
    draw.rectangle(
        (size[0] * 0.12, size[1] * 0.58, size[0] * 0.62, size[1] * 0.64),
        fill="#222222",
    )
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class PhaseOneFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        _tmp.cleanup()

    def test_ingest_analyze_search_and_selectable_results(self) -> None:
        first = sample_image("#F5EFE6", "#DFAE92")
        response = self.client.post(
            "/api/analyze",
            files={"file": ("warm-poster.png", first, "image/png")},
            data={
                "source_type": "company_published",
                "product_category": "吸奶器",
                "rights_note": "公司内部使用",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        case = response.json()
        self.assertEqual(case["product_category"], "吸奶器")
        self.assertEqual(case["trust_status"], "ai_unverified")
        self.assertEqual(case["image"]["source_type"], "company_published")
        self.assertIn("layout", case["analysis"])
        self.assertEqual(case["analysis"]["version"], 1)

        second = sample_image("#EAF3FF", "#596DFF", vertical=False)
        second_response = self.client.post(
            "/api/analyze",
            files={"file": ("tech-banner.png", second, "image/png")},
            data={
                "source_type": "external_reference",
                "product_category": "恒温杯",
                "source_url": "https://example.com/reference",
            },
        )
        self.assertEqual(second_response.status_code, 200, second_response.text)

        text_search = self.client.post(
            "/api/search",
            data={"query_text": "吸奶器", "product": "吸奶器"},
        )
        self.assertEqual(text_search.status_code, 200, text_search.text)
        hits = text_search.json()
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["case"]["id"], case["id"])
        self.assertTrue(hits[0]["reasons"])

        reference_search = self.client.post(
            "/api/search",
            files={"reference_image": ("reference.png", first, "image/png")},
        )
        self.assertEqual(reference_search.status_code, 200, reference_search.text)
        self.assertGreaterEqual(len(reference_search.json()), 1)

        duplicate = self.client.post(
            "/api/analyze",
            files={"file": ("warm-copy.png", first, "image/png")},
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(duplicate.json()["id"], case["id"])


if __name__ == "__main__":
    unittest.main()
