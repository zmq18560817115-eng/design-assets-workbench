from __future__ import annotations

import io
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

_tmp = tempfile.TemporaryDirectory(prefix="design-assets-v2-test-")
_root = Path(_tmp.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_root / "uploads")
os.environ["VISION_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import LayoutBlueprintInput  # noqa: E402
from app.agents import run_pipeline  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402


def image_bytes(color: str = "#edf3f8") -> bytes:
    image = Image.new("RGB", (600, 800), color)
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


class LayoutBlueprintRequirementV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def blueprint_payload(self) -> dict:
        return {
            "canvas_ratio": "3:4", "orientation": "portrait",
            "grid_columns": 6, "grid_rows": 12,
            "margins": {"top": .05, "right": .05, "bottom": .05, "left": .05},
            "alignment": "center", "reading_flow": "top-to-bottom",
            "information_density": "medium", "text_image_ratio": .4,
            "modules_json": [{
                "id": "module-1", "type": "main_title", "label": "主标题",
                "x": .1, "y": .05, "width": .8, "height": .1,
                "importance": 1, "alignment": "center",
                "content_summary": "", "confidence": .9,
            }],
            "module_count": 1, "review_status": "ai_generated",
            "model_name": "fallback-test", "prompt_version": "layout-blueprint-v2",
        }

    def test_01_blueprint_validation(self):
        base = self.blueprint_payload()
        valid = LayoutBlueprintInput.model_validate(base)
        self.assertTrue(valid.layout_signature.startswith("lbp2-"))
        for patch in (
            {"x": -0.1},
            {"x": .8, "width": .4},
        ):
            with self.assertRaises(ValidationError):
                LayoutBlueprintInput.model_validate({
                    **base,
                    "modules_json": [{**base["modules_json"][0], **patch}],
                })
        with self.assertRaises(ValidationError):
            LayoutBlueprintInput.model_validate({**base, "module_count": 2})

    def test_02_blueprint_create_revise_verify_versions_and_fallback(self):
        upload = self.client.post(
            "/api/analyze",
            files={"file": ("poster.png", image_bytes(), "image/png")},
            data={"asset_category": "layout"},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        case_id = upload.json()["id"]
        current = self.client.get(f"/api/cases/{case_id}/layout-blueprint")
        self.assertEqual(current.status_code, 200, current.text)
        payload = {**current.json(), "editor": "测试负责人"}
        revised = self.client.patch(
            f"/api/cases/{case_id}/layout-blueprint?expected_version={payload['version']}",
            json=payload,
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["review_status"], "corrected")
        verified = self.client.post(
            f"/api/cases/{case_id}/layout-blueprint/verify",
            json={"editor": "测试负责人", "version": revised.json()["version"]},
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["review_status"], "verified")
        versions = self.client.get(f"/api/cases/{case_id}/layout-blueprint/versions")
        self.assertGreaterEqual(len(versions.json()), 3)
        fallback = self.client.post(f"/api/cases/{case_id}/layout-blueprint/regenerate")
        self.assertEqual(fallback.status_code, 200, fallback.text)
        self.assertIn("fallback", fallback.json()["model_name"])

    def requirement_payload(self) -> dict:
        return {
            "title": "小红书产品卖点介绍", "product_category": "奶瓶",
            "channel": "小红书", "content_purpose": "卖点说明",
            "target_audience": "新手妈妈", "canvas_ratio": "3:4",
            "information_density": "medium",
            "required_modules_json": ["main_title", "product_image"],
            "optional_modules_json": ["cta"],
            "forbidden_modules_json": ["parameter_table"],
            "selling_points_json": ["防胀气"], "style_keywords_json": ["可信"],
            "raw_requirement": "介绍奶瓶核心卖点",
            "reference_case_ids_json": [], "creator": "测试产品经理",
            "status": "draft",
        }

    def test_03_requirement_create_update_confirm_and_validation(self):
        project = self.client.post("/api/projects", json={
            "name": "Requirement gate project", "description": "real brief test",
            "business_line": "maternal", "status": "active", "is_gold": False,
        })
        self.assertEqual(project.status_code, 200, project.text)
        payload = {
            **self.requirement_payload(), "project_id": project.json()["id"],
            "product_name": "Test product", "page_role": "selling-point",
            "brief_source": "feishu://real-brief/test", "reviewer": "Test owner",
        }
        created = self.client.post("/api/business-requirements", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        requirement_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/business-requirements/{requirement_id}",
            json={**created.json(), "title": "产品卖点介绍（修订）"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        confirmed = self.client.post(
            f"/api/business-requirements/{requirement_id}/confirm",
            json={"reviewer": "Test owner", "notes": "fields checked"},
        )
        self.assertEqual(confirmed.json()["status"], "confirmed")
        conflict = self.client.post(
            "/api/business-requirements",
            json={**payload, "title": "冲突", "forbidden_modules_json": ["main_title"]},
        )
        self.assertEqual(conflict.status_code, 422)
        missing = self.client.post(
            "/api/business-requirements",
            json={**payload, "title": "无效参考", "reference_case_ids_json": [999999]},
        )
        self.assertEqual(missing.status_code, 400)
        # Keep this test isolated even when a developer explicitly points the
        # suite at a persistent local database.
        db = SessionLocal()
        try:
            db.query(models.BusinessRequirementReviewEvent).filter_by(requirement_id=requirement_id).delete()
            db.query(models.BusinessRequirement).filter_by(id=requirement_id).delete()
            db.query(models.Project).filter_by(id=project.json()["id"]).delete()
            db.commit()
        finally:
            db.close()

    def test_04_invalid_ai_json_falls_back_and_strict_mode_errors(self):
        path = _root / "invalid-ai.png"
        path.write_bytes(image_bytes("#faf2ea"))
        with (
            patch("app.agents.pipeline._vlm_enabled", return_value=True),
            patch(
                "app.agents.pipeline.vlm.analyze_image",
                side_effect=ValueError("模型返回非法JSON"),
            ),
        ):
            fallback = run_pipeline(str(path), strict_vlm=False)
            self.assertEqual(fallback.analyzed_by, "启发式规则")
            with self.assertRaisesRegex(ValueError, "非法JSON"):
                run_pipeline(str(path), strict_vlm=True)

    def test_05_upload_endpoints_reject_invalid_source_type_before_writing(self):
        before = set(_root.joinpath("uploads").glob("*"))
        single = self.client.post(
            "/api/analyze",
            files={"file": ("bad.png", image_bytes(), "image/png")},
            data={"source_type": "unused_internal"},
        )
        batch = self.client.post(
            "/api/analyze/batch",
            files=[("files", ("bad.png", image_bytes(), "image/png"))],
            data={"source_type": "internal_reference"},
        )
        self.assertEqual(single.status_code, 422, single.text)
        self.assertEqual(batch.status_code, 422, batch.text)
        self.assertEqual(before, set(_root.joinpath("uploads").glob("*")))
