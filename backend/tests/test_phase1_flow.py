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
                "asset_category": "layout",
                "asset_subcategory": "层级分类对比",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        case = response.json()
        self.assertEqual(case["product_category"], "吸奶器")
        self.assertEqual(case["trust_status"], "ai_unverified")
        self.assertEqual(case["asset_category"], "layout")
        self.assertEqual(case["asset_subcategory"], "层级分类对比")
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
                "asset_category": "style",
                "asset_subcategory": "电商风格",
            },
        )
        self.assertEqual(second_response.status_code, 200, second_response.text)

        layout_library = self.client.get(
            "/api/cases", params={"asset_category": "layout"}
        )
        self.assertEqual(layout_library.status_code, 200)
        self.assertTrue(layout_library.json())
        self.assertTrue(
            all(item["asset_category"] == "layout" for item in layout_library.json())
        )

        review = self.client.patch(
            f"/api/cases/{case['id']}/review",
            json={
                "reviewer": "测试设计师",
                "trust_status": "company_recommended",
                "review_decision": "adopt",
                "review_notes": "符合公司母婴产品信息层级规范",
                "business_line": "母婴",
                "channel": "小红书",
                "campaign_stage": "新品种草",
                "business_goal": "建立产品差异认知",
                "layout_type": "人工校正双栏版式",
                "style_tags": ["公司简约风", "温暖可信"],
                "why_good": ["信息层级清晰"],
                "reusable_methods": ["保持标题与产品卖点的三级层级"],
            },
        )
        self.assertEqual(review.status_code, 200, review.text)
        reviewed = review.json()
        self.assertEqual(reviewed["trust_status"], "company_recommended")
        self.assertEqual(reviewed["business_line"], "母婴")
        self.assertEqual(reviewed["analysis"]["version"], 2)
        self.assertEqual(
            reviewed["analysis"]["layout"]["layout_type"], "人工校正双栏版式"
        )
        versions = self.client.get(f"/api/cases/{case['id']}/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertEqual(len(versions.json()), 2)
        self.assertEqual(versions.json()[0]["source"], "manual")

        project = self.client.post(
            "/api/projects",
            json={
                "name": "黄金样本测试项目",
                "description": "人工确认的业务标准案例",
                "business_line": "母婴",
                "status": "active",
                "is_gold": True,
            },
        )
        self.assertEqual(project.status_code, 200, project.text)
        project_id = project.json()["id"]
        assigned = self.client.patch(
            f"/api/cases/{case['id']}/project",
            json={"project_id": project_id},
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.json()["project_id"], project_id)

        preference = self.client.post(
            f"/api/cases/{case['id']}/preferences",
            json={
                "event_type": "favorite",
                "value": 1,
                "actor": "测试设计师",
                "context": "适合作为新品种草参考",
            },
        )
        self.assertEqual(preference.status_code, 200, preference.text)
        preference_summary = self.client.get(
            f"/api/cases/{case['id']}/preferences"
        )
        self.assertEqual(preference_summary.json()["favorite"], 1)

        projects = self.client.get("/api/projects")
        self.assertEqual(projects.status_code, 200)
        self.assertEqual(projects.json()[0]["case_count"], 1)
        concept = self.client.get("/api/concept")
        self.assertEqual(concept.status_code, 200, concept.text)
        self.assertGreater(concept.json()["weighted_total"], 0)
        self.assertIn("trust_counts", concept.json())

        reanalyzed = self.client.post(f"/api/cases/{case['id']}/reanalyze")
        self.assertEqual(reanalyzed.status_code, 200, reanalyzed.text)
        self.assertEqual(reanalyzed.json()["analysis"]["version"], 3)
        self.assertEqual(reanalyzed.json()["trust_status"], "ai_unverified")

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
