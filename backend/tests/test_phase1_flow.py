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

        filtered = self.client.get(
            "/api/cases",
            params={
                "project_id": project_id,
                "trust_status": "ai_unverified",
            },
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual([item["id"] for item in filtered.json()], [case["id"]])
        model_only = self.client.get(
            "/api/cases",
            params={"project_id": project_id, "analysis_mode": "model"},
        )
        self.assertEqual(model_only.status_code, 200, model_only.text)
        self.assertEqual(model_only.json(), [])
        local_only = self.client.get(
            "/api/cases",
            params={"project_id": project_id, "analysis_mode": "local"},
        )
        self.assertEqual(local_only.status_code, 200, local_only.text)
        self.assertEqual([item["id"] for item in local_only.json()], [case["id"]])

        overview = self.client.get("/api/training/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertGreaterEqual(overview.json()["unreviewed_cases"], 1)
        self.assertIn("layout", overview.json()["category_coverage"])

        batch_review = self.client.post(
            "/api/training/batch-review",
            json={
                "case_ids": [case["id"]],
                "action": "confirm",
                "reviewer": "测试设计总监",
                "review_notes": "批量确认进入可信样本",
                "business_line": "母婴",
            },
        )
        self.assertEqual(batch_review.status_code, 200, batch_review.text)
        self.assertEqual(batch_review.json()["updated_count"], 1)
        self.assertEqual(
            self.client.get(f"/api/cases/{case['id']}").json()["trust_status"],
            "verified",
        )

        preference_search = self.client.post(
            "/api/search",
            data={"query_text": "", "limit": "10"},
        )
        self.assertEqual(preference_search.status_code, 200, preference_search.text)
        self.assertEqual(preference_search.json()[0]["case"]["id"], case["id"])
        self.assertTrue(
            any(
                reason in {"人工确认样本", "真实业务采用信号", "黄金项目证据"}
                for reason in preference_search.json()[0]["reasons"]
            )
        )

        recommendation = self.client.post(
            "/api/recommend",
            data={
                "text": "母婴新品首发，需要清晰排版",
                "industry": "母婴",
                "channel": "小红书",
                "campaign_stage": "新品首发",
                "business_goal": "建立专业信任",
            },
        )
        self.assertEqual(recommendation.status_code, 200, recommendation.text)
        recommendation_data = recommendation.json()
        self.assertTrue(recommendation_data["preference_applied"])
        self.assertEqual(recommendation_data["company_evidence"]["trusted_cases"], 1)
        self.assertIn("公司偏好约束", recommendation_data["prompt"])
        self.assertIn("业务约束", recommendation_data["prompt"])
        self.assertIn(case["id"], recommendation_data["evidence_case_ids"])
        self.assertGreater(recommendation_data["run_id"], 0)

        isolated_recommendation = self.client.post(
            "/api/recommend",
            data={"text": "new launch", "industry": "other-line"},
        )
        self.assertEqual(
            isolated_recommendation.status_code,
            200,
            isolated_recommendation.text,
        )
        self.assertFalse(isolated_recommendation.json()["preference_applied"])
        scoped_concept = self.client.get(
            "/api/concept", params={"business_line": "other-line"}
        )
        self.assertEqual(scoped_concept.status_code, 200, scoped_concept.text)
        self.assertEqual(scoped_concept.json()["evidence_count"], 0)

        service_feedback = self.client.post(
            f"/api/service-runs/{recommendation_data['run_id']}/feedback",
            json={
                "outcome": "adopted",
                "actor": "测试业务负责人",
                "notes": "方向进入正式设计",
            },
        )
        self.assertEqual(service_feedback.status_code, 200, service_feedback.text)
        self.assertIn(
            case["id"], service_feedback.json()["evidence_cases_updated"]
        )
        service_runs = self.client.get("/api/service-runs")
        self.assertEqual(service_runs.status_code, 200, service_runs.text)
        self.assertTrue(
            any(
                item["id"] == recommendation_data["run_id"]
                and item["status"] == "adopted"
                for item in service_runs.json()
            )
        )
        stored_run = next(
            item
            for item in service_runs.json()
            if item["id"] == recommendation_data["run_id"]
        )
        self.assertEqual(stored_run["channel"], "小红书")
        self.assertEqual(stored_run["campaign_stage"], "新品首发")
        self.assertEqual(stored_run["business_goal"], "建立专业信任")
        overview_after_service = self.client.get("/api/training/overview").json()
        self.assertEqual(overview_after_service["service_runs"], 2)
        self.assertEqual(overview_after_service["adopted_service_runs"], 1)

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
