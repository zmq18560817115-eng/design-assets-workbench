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
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageDraw

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-test-")
_root = Path(_tmp.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_root / "uploads")
os.environ["VISION_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import config, crud, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import LayoutBlueprintInput  # noqa: E402


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

    @patch.object(config, "ENABLE_LAYOUT_DIRECTIONS", True)
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
        auto_blueprints = self.client.get(
            f"/api/cases/{case['id']}/layout-blueprints"
        )
        self.assertEqual(auto_blueprints.status_code, 200, auto_blueprints.text)
        self.assertEqual(len(auto_blueprints.json()), 1)
        auto_blueprint = auto_blueprints.json()[0]
        self.assertEqual(auto_blueprint["version"], 1)
        self.assertEqual(auto_blueprint["canvas_ratio"], "2:3")
        self.assertEqual(auto_blueprint["orientation"], "portrait")
        self.assertGreaterEqual(auto_blueprint["module_count"], 2)
        self.assertLessEqual(auto_blueprint["module_count"], 12)
        self.assertIn("region-detection", auto_blueprint["model_name"])
        self.assertTrue(auto_blueprint["model_name"])
        self.assertTrue(auto_blueprint["prompt_version"])

        blueprint_payload = LayoutBlueprintInput(
            canvas_ratio="2:3",
            orientation="portrait",
            grid_columns=6,
            grid_rows=12,
            margins={"top": 0.04, "right": 0.06, "bottom": 0.05, "left": 0.06},
            alignment="center",
            reading_flow="top-to-bottom",
            focal_region={"x": 0.18, "y": 0.22, "width": 0.64, "height": 0.46},
            information_density="medium",
            text_image_ratio=0.35,
            modules_json=[
                {
                    "id": "module-1",
                    "type": "title",
                    "x": 0.08,
                    "y": 0.05,
                    "width": 0.84,
                    "height": 0.12,
                    "priority": 1,
                    "alignment": "center",
                    "description": "主标题区域",
                },
                {
                    "id": "module-2",
                    "type": "product_image",
                    "x": 0.18,
                    "y": 0.22,
                    "width": 0.64,
                    "height": 0.46,
                    "priority": 2,
                    "alignment": "center",
                    "description": "产品主视觉",
                },
            ],
            model_name="mock-layout-model",
            prompt_version="layout-blueprint-v1",
        )
        with SessionLocal() as db:
            blueprint = crud.create_layout_blueprint(
                db,
                case["id"],
                blueprint_payload,
            )
            serialized = crud.serialize_layout_blueprint(blueprint)
            self.assertEqual(serialized["version"], 2)
            self.assertEqual(serialized["module_count"], 2)
            self.assertEqual(serialized["modules_json"][1]["x"], 0.18)
            revised_payload = blueprint_payload.model_copy(
                update={
                    "review_status": "human_edited",
                    "editor": "测试设计师",
                }
            )
            revised = crud.revise_layout_blueprint(
                db,
                blueprint.id,
                revised_payload,
            )
            self.assertEqual(revised.version, 3)
            self.assertEqual(revised.review_status, "human_edited")
            self.assertEqual(len(crud.list_layout_blueprints(db, case["id"])), 3)
            revised_again = crud.revise_layout_blueprint(
                db,
                blueprint.id,
                revised_payload,
            )
            self.assertEqual(revised_again.version, 4)
            self.assertEqual(len(crud.list_layout_blueprints(db, case["id"])), 4)
        latest_versions = self.client.get(
            f"/api/cases/{case['id']}/layout-blueprints"
        )
        self.assertEqual(latest_versions.status_code, 200, latest_versions.text)
        self.assertEqual(
            [item["version"] for item in latest_versions.json()],
            [4, 3, 2, 1],
        )
        verified = self.client.post(
            f"/api/layout-blueprints/{latest_versions.json()[0]['id']}/verify",
            json={"editor": "layout-review-lead"},
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["version"], 5)
        self.assertEqual(verified.json()["review_status"], "verified")
        pattern_payload = {
            "name": "竖版标题主视觉转化模式",
            "description": "标题、产品主视觉、辅助信息和行动引导自上而下排列",
            "source_blueprint_ids": [verified.json()["id"]],
            "industry_tags": ["母婴"],
            "scene_tags": ["新品种草"],
            "channel_tags": ["小红书"],
            "business_goal_tags": ["建立产品差异认知"],
            "usage_notes": "适合单一产品卖点逐级展开",
            "editor": "layout-review-lead",
        }
        pattern = self.client.post("/api/layout-patterns", json=pattern_payload)
        self.assertEqual(pattern.status_code, 200, pattern.text)
        self.assertEqual(pattern.json()["version"], 1)
        self.assertEqual(pattern.json()["review_status"], "human_edited")
        self.assertEqual(
            pattern.json()["source_case_ids"],
            [case["id"]],
        )
        self.assertEqual(
            pattern.json()["modules_json"],
            verified.json()["modules_json"],
        )
        rejected_pattern = self.client.post(
            "/api/layout-patterns",
            json={
                **pattern_payload,
                "name": "不应沉淀的未确认模式",
                "source_blueprint_ids": [auto_blueprint["id"]],
            },
        )
        self.assertEqual(rejected_pattern.status_code, 400)
        verified_pattern = self.client.post(
            f"/api/layout-patterns/{pattern.json()['id']}/verify",
            json={
                "editor": "layout-library-owner",
                "representative_case_ids": pattern.json()["source_case_ids"][:1],
                "name_confirmed": True,
                "scenes_confirmed": True,
                "modules_confirmed": True,
                "design_owner_confirmed": True,
            },
        )
        self.assertEqual(verified_pattern.status_code, 422, verified_pattern.text)
        self.assertIn("至少3个不同公司案例", str(verified_pattern.json()))
        # Preserve the legacy search/direction fixture below without bypassing
        # the production verification endpoint tested above.
        with SessionLocal() as db:
            fixture_pattern = db.get(models.LayoutPattern, pattern.json()["id"])
            fixture_pattern.review_status = "verified"
            db.commit()
        pattern_library = self.client.get(
            "/api/layout-patterns",
            params={
                "scene": "新品种草",
                "channel": "小红书",
                "review_status": "verified",
            },
        )
        self.assertEqual(pattern_library.status_code, 200, pattern_library.text)
        self.assertEqual(
            [item["id"] for item in pattern_library.json()],
            [pattern.json()["id"]],
        )
        requirement = self.client.post(
            "/api/business-requirements",
            json={
                "title": "吸奶器新品小红书种草长图",
                "request_text": "突出吸力模式、舒适度和便携性，形成清晰的购买理由",
                "industry": "母婴",
                "product_category": "吸奶器",
                "channel": "小红书",
                "canvas_ratio": "2:3",
                "orientation": "portrait",
                "campaign_stage": "新品种草",
                "business_goal": "建立产品差异认知",
                "target_audience": "新手妈妈",
                "key_message": "舒适高效地完成吸奶",
                "mandatory_elements": ["产品主图", "三项卖点", "行动引导"],
                "information_density": "medium",
                "reference_case_ids": [case["id"]],
                "created_by": "业务设计师",
                "status": "ready",
            },
        )
        self.assertEqual(requirement.status_code, 200, requirement.text)
        self.assertEqual(
            requirement.json()["mandatory_elements"],
            ["产品主图", "三项卖点", "行动引导"],
        )
        matched = self.client.post(
            f"/api/business-requirements/{requirement.json()['id']}/match"
        )
        self.assertEqual(matched.status_code, 200, matched.text)
        self.assertEqual(
            matched.json()["pattern_matches"][0]["pattern"]["id"],
            pattern.json()["id"],
        )
        self.assertEqual(
            matched.json()["case_matches"][0]["case_id"],
            case["id"],
        )
        self.assertIn(
            "需求指定参考案例",
            matched.json()["case_matches"][0]["reasons"],
        )
        with patch.object(config, "ENABLE_LAYOUT_DIRECTIONS", True):
            directions = self.client.post(
                f"/api/business-requirements/{requirement.json()['id']}/directions/generate"
            )
        self.assertEqual(directions.status_code, 200, directions.text)
        self.assertEqual(len(directions.json()["directions"]), 3)
        self.assertEqual(
            {
                item["strategy_level"]
                for item in directions.json()["directions"]
            },
            {"conservative", "balanced", "exploratory"},
        )
        for direction in directions.json()["directions"]:
            self.assertTrue(direction["source_pattern_ids"])
            self.assertTrue(direction["source_case_ids"])
            self.assertTrue(direction["modules_json"])
            self.assertEqual(
                direction["module_count"],
                len(direction["modules_json"]),
            )
            self.assertTrue(direction["model_name"])
            self.assertTrue(direction["prompt_version"])
            self.assertEqual(direction["generation_mode"], "heuristic")
            self.assertIn("模型未配置", direction["failure_reason"])
        first_direction = directions.json()["directions"][0]
        with SessionLocal() as db:
            preference_count_before = db.query(models.PreferenceEvent).count()
        selected_feedback = self.client.post(
            f"/api/layout-directions/{first_direction['id']}/feedback",
            json={
                "action": "selected",
                "actor": "业务设计师",
                "notes": "信息层级最符合当前上线节奏",
            },
        )
        self.assertEqual(
            selected_feedback.status_code,
            200,
            selected_feedback.text,
        )
        adjustment_feedback = self.client.post(
            f"/api/layout-directions/{first_direction['id']}/feedback",
            json={
                "action": "adjustment_requested",
                "actor": "业务负责人",
                "notes": "主视觉再扩大，底部行动引导上移",
            },
        )
        self.assertEqual(adjustment_feedback.status_code, 200)
        adjusted_modules = first_direction["modules_json"]
        adjusted_modules[1]["width"] = min(
            1 - adjusted_modules[1]["x"],
            adjusted_modules[1]["width"] + 0.02,
        )
        confirmed_feedback = self.client.post(
            f"/api/layout-directions/{first_direction['id']}/feedback",
            json={
                "action": "adjusted_confirmed",
                "actor": "业务负责人",
                "notes": "调整版确认",
                "adjusted_modules_json": adjusted_modules,
            },
        )
        self.assertEqual(
            confirmed_feedback.status_code,
            200,
            confirmed_feedback.text,
        )
        self.assertEqual(
            confirmed_feedback.json()["adjusted_modules_json"],
            adjusted_modules,
        )
        invalid_adjustment = self.client.post(
            f"/api/layout-directions/{first_direction['id']}/feedback",
            json={
                "action": "adjusted_confirmed",
                "actor": "业务负责人",
                "adjusted_modules_json": [
                    {
                        "id": "outside",
                        "type": "title",
                        "x": 0.9,
                        "y": 0.1,
                        "width": 0.2,
                        "height": 0.1,
                        "priority": 1,
                    }
                ],
            },
        )
        self.assertEqual(invalid_adjustment.status_code, 422)
        feedback_history = self.client.get(
            f"/api/layout-directions/{first_direction['id']}/feedback"
        )
        self.assertEqual(feedback_history.status_code, 200)
        self.assertEqual(
            [item["action"] for item in feedback_history.json()],
            ["selected", "adjustment_requested", "adjusted_confirmed"],
        )
        with SessionLocal() as db:
            self.assertEqual(
                db.query(models.PreferenceEvent).count(),
                preference_count_before,
            )
        regenerated_directions = self.client.post(
            f"/api/business-requirements/{requirement.json()['id']}/directions/generate"
        )
        self.assertEqual(regenerated_directions.status_code, 200)
        self.assertEqual(
            regenerated_directions.json()["generation_version"],
            2,
        )
        with (
            patch("app.crud.config.LLM_API_KEY", "test-key"),
            patch("app.crud.config.LLM_MODEL", "test-model"),
            patch(
                "app.crud.llm.chat_json",
                side_effect=RuntimeError("simulated provider timeout"),
            ),
        ):
            fallback_directions = self.client.post(
                f"/api/business-requirements/{requirement.json()['id']}/directions/generate"
            )
        self.assertEqual(
            fallback_directions.status_code,
            200,
            fallback_directions.text,
        )
        self.assertEqual(
            fallback_directions.json()["generation_version"],
            3,
        )
        for direction in fallback_directions.json()["directions"]:
            self.assertEqual(direction["generation_mode"], "heuristic")
            self.assertEqual(
                direction["model_name"],
                "heuristic-layout-direction",
            )
            self.assertIn("RuntimeError", direction["failure_reason"])
        direction_history = self.client.get(
            f"/api/business-requirements/{requirement.json()['id']}/directions"
        )
        self.assertEqual(direction_history.status_code, 200)
        self.assertEqual(len(direction_history.json()), 9)
        generated = self.client.post(
            f"/api/cases/{case['id']}/layout-blueprints/generate"
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()["version"], 6)
        self.assertEqual(generated.json()["orientation"], "portrait")
        api_revised = self.client.post(
            f"/api/layout-blueprints/{generated.json()['id']}/revise",
            json=revised_payload.model_dump(mode="json"),
        )
        self.assertEqual(api_revised.status_code, 200, api_revised.text)
        self.assertEqual(api_revised.json()["version"], 7)
        self.assertEqual(api_revised.json()["review_status"], "human_edited")
        with self.assertRaises(ValidationError):
            LayoutBlueprintInput(
                orientation="portrait",
                modules_json=[
                    {
                        "id": "outside",
                        "type": "title",
                        "x": 0.8,
                        "y": 0.1,
                        "width": 0.3,
                        "height": 0.2,
                    }
                ],
            )

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
        quality = self.client.get(
            "/api/training/review-quality",
            params={"project_id": project_id},
        )
        self.assertEqual(quality.status_code, 200, quality.text)
        case_quality = next(
            item for item in quality.json() if item["case_id"] == case["id"]
        )
        self.assertFalse(case_quality["ready"])
        self.assertIn("尚未完成真实视觉模型拆解", case_quality["warnings"])

        overview = self.client.get("/api/training/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertGreaterEqual(overview.json()["unreviewed_cases"], 1)
        self.assertIn("layout", overview.json()["category_coverage"])
        self.assertTrue(overview.json()["training_matrix"])
        matrix_row = overview.json()["training_matrix"][0]
        self.assertEqual(matrix_row["project_id"], project_id)
        self.assertIn("layout", matrix_row["cells"])
        self.assertFalse(matrix_row["cells"]["layout"]["ready"])
        task_pack = self.client.get("/api/training/task-pack")
        self.assertEqual(task_pack.status_code, 200, task_pack.text)
        self.assertGreater(task_pack.json()["total_tasks"], 0)
        first_task = task_pack.json()["tasks"][0]
        self.assertEqual(first_task["project_id"], project_id)
        self.assertIn(first_task["priority"], {"urgent", "high"})
        self.assertTrue(first_task["acceptance_criteria"])
        readiness = self.client.get("/api/training/readiness")
        self.assertEqual(readiness.status_code, 200, readiness.text)
        line_readiness = next(
            item
            for item in readiness.json()
            if item["business_line"] == "母婴"
        )
        self.assertEqual(line_readiness["stage"], "collect")
        self.assertEqual(line_readiness["service_mode"], "reference_only")
        self.assertTrue(line_readiness["weekly_actions"])
        self.assertTrue(line_readiness["owner_role"])
        self.assertTrue(line_readiness["acceptance_criteria"])
        self.assertEqual(
            line_readiness["gates"]["company_assets"]["current"],
            1,
        )

        batch_review = self.client.post(
            "/api/training/batch-review",
            json={
                "case_ids": [case["id"]],
                "action": "confirm",
                "reviewer": "测试设计总监",
                "review_notes": "批量确认进入可信样本",
                "business_line": "母婴",
                "keep_reasons": ["keep clear hierarchy"],
                "avoid_reasons": ["avoid crowded claims"],
            },
        )
        self.assertEqual(batch_review.status_code, 200, batch_review.text)
        self.assertEqual(batch_review.json()["updated_count"], 1)
        self.assertEqual(
            self.client.get(f"/api/cases/{case['id']}").json()["trust_status"],
            "verified",
        )
        concept_data = self.client.get(
            "/api/concept", params={"business_line": "母婴"}
        ).json()
        self.assertEqual(
            concept_data["explicit_guidance"]["keep"][0]["text"],
            "keep clear hierarchy",
        )
        self.assertEqual(
            concept_data["explicit_guidance"]["avoid"][0]["text"],
            "avoid crowded claims",
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
        self.assertEqual(recommendation_data["focus_category"], "layout")
        self.assertEqual(recommendation_data["company_usage_mode"], "reference_only")
        self.assertEqual(recommendation_data["company_evidence"]["trusted_cases"], 1)
        self.assertIn("公司偏好约束", recommendation_data["prompt"])
        self.assertIn("业务约束", recommendation_data["prompt"])
        self.assertIn("keep clear hierarchy", recommendation_data["prompt"])
        self.assertIn("avoid crowded claims", recommendation_data["prompt"])
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
        self.assertEqual(stored_run["focus_category"], "layout")
        self.assertEqual(stored_run["channel"], "小红书")
        self.assertEqual(stored_run["campaign_stage"], "新品首发")
        self.assertEqual(stored_run["business_goal"], "建立专业信任")
        run_detail = self.client.get(
            f"/api/service-runs/{recommendation_data['run_id']}"
        )
        self.assertEqual(run_detail.status_code, 200, run_detail.text)
        self.assertEqual(run_detail.json()["focus_category"], "layout")
        self.assertEqual(run_detail.json()["channel"], "小红书")
        self.assertEqual(
            run_detail.json()["result"]["prompt"],
            recommendation_data["prompt"],
        )
        self.assertEqual(
            run_detail.json()["company_profile_snapshot"]["scope"],
            "母婴 / layout",
        )
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

        with (
            patch("app.main.config.vlm_enabled", return_value=True),
            patch(
                "app.main.vlm.suggest_asset_category",
                return_value={
                    "category": "style",
                    "confidence": 91,
                    "reason": "visual language is the primary reusable value",
                    "signals": ["consistent illustration", "distinctive texture"],
                },
            ),
        ):
            suggestion_response = self.client.post(
                "/api/training/batch-suggest-categories",
                json={"case_ids": [case["id"]]},
            )
        self.assertEqual(
            suggestion_response.status_code,
            200,
            suggestion_response.text,
        )
        self.assertEqual(suggestion_response.json()["suggested_count"], 1)
        suggestions = self.client.get("/api/training/category-suggestions")
        self.assertEqual(suggestions.status_code, 200, suggestions.text)
        self.assertEqual(suggestions.json()[0]["suggested_category"], "style")

        with (
            patch("app.main.config.vlm_enabled", return_value=True),
            patch(
                "app.main.vlm.suggest_asset_category",
                return_value={
                    "category": "style",
                    "confidence": 93,
                    "reason": "background classification",
                    "signals": ["visual signal"],
                },
            ),
        ):
            job_response = self.client.post(
                "/api/training/category-suggestion-jobs",
                json={"case_ids": [case["id"]]},
            )
        self.assertEqual(job_response.status_code, 200, job_response.text)
        job = self.client.get(
            f"/api/training/category-suggestion-jobs/{job_response.json()['id']}"
        )
        self.assertEqual(job.status_code, 200, job.text)
        self.assertEqual(job.json()["status"], "completed")
        self.assertEqual(job.json()["succeeded"], 1)
        latest_job = self.client.get(
            "/api/training/category-suggestion-job-status"
        )
        self.assertEqual(latest_job.status_code, 200, latest_job.text)
        self.assertEqual(latest_job.json()["id"], job.json()["id"])
        discovery = self.client.get("/api/training/category-discovery")
        self.assertEqual(discovery.status_code, 200, discovery.text)
        line_discovery = next(
            item
            for item in discovery.json()
            if item["business_line"] == "母婴"
        )
        self.assertEqual(
            line_discovery["candidates"]["style"][0]["case_id"],
            case["id"],
        )

        categorized = self.client.post(
            "/api/training/batch-categorize",
            json={
                "case_ids": [case["id"]],
                "asset_category": "style",
                "actor": "测试素材管理员",
            },
        )
        self.assertEqual(categorized.status_code, 200, categorized.text)
        self.assertEqual(categorized.json()["updated_count"], 1)
        self.assertEqual(
            self.client.get(f"/api/cases/{case['id']}").json()["asset_category"],
            "style",
        )
        reviewed_suggestion = self.client.get(
            "/api/training/category-suggestions"
        ).json()[0]
        self.assertEqual(reviewed_suggestion["status"], "accepted")
        self.assertEqual(reviewed_suggestion["reviewer"], "测试素材管理员")


if __name__ == "__main__":
    unittest.main()
