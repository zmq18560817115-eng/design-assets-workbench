from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.main import (
    _find_annotation_original_case,
    auto_decompose_disinfection_case,
    finalize_disinfection_decomposition_run,
    set_disinfection_annotation_recommendation,
    update_disinfection_annotation,
    verify_disinfection_annotation,
)


class DisinfectionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="disinfection-workflow-")
        root = Path(self.temp.name)
        self.engine = create_engine(f"sqlite:///{root / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.uploads = root / "uploads"
        self.uploads.mkdir()
        PILImage.new("RGB", (600, 800), "white").save(self.uploads / "case.png")
        image = models.Image(
            url="/uploads/case.png", filename="case.png",
            source_type="company_published",
        )
        self.db.add(image)
        self.db.flush()
        self.case = models.Case(
            image_id=image.id, name="case", product_category="消毒柜",
            page_role="product_display",
        )
        self.db.add(self.case)
        self.db.flush()
        for index in range(3):
            self.db.add(models.DisinfectionAnnotation(
                source_sha256=f"sha-{index}",
                source_type="company_published",
                status="verified",
                annotation_verified=True,
                company_recommended=True,
                recommendation_status="recommended",
                recommendation_confirmed_by_lead=True,
                dataset_split="calibration",
                canvas_width=600,
                canvas_height=800,
                orientation="portrait",
                page_role="product_display",
                regions_json=json.dumps([{
                    "id": "p", "type": "product_image", "color": "blue",
                    "x": .1, "y": .2, "width": .6, "height": .5,
                    "confidence": 1,
                }]),
            ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_model_failure_enters_review_without_fake_blueprint(self):
        with (
            patch("app.main.config.UPLOAD_DIR", self.uploads),
            patch("app.main.config.vlm_enabled", return_value=True),
            patch("app.main.run_pipeline", side_effect=RuntimeError("provider down")),
        ):
            result = auto_decompose_disinfection_case(self.case.id, self.db)
        self.assertEqual("review_required", result["status"])
        self.assertIsNone(result["blueprint_id"])
        self.assertEqual({}, result["initial_ai_blueprint"])
        self.assertIn("model_failure", result["failure_reasons"][0])
        self.assertEqual(
            0,
            self.db.query(models.LayoutBlueprint)
            .filter(models.LayoutBlueprint.case_id == self.case.id)
            .count(),
        )

    def test_generic_route_logic_accepts_another_product_category(self):
        self.case.product_category = "奶瓶"
        self.db.commit()
        with (
            patch("app.main.config.UPLOAD_DIR", self.uploads),
            patch("app.main.config.vlm_enabled", return_value=False),
        ):
            result = auto_decompose_disinfection_case(self.case.id, self.db)
        self.assertEqual("review_required", result["status"])
        self.assertIn("vision_model_unavailable", result["failure_reasons"][0])

    def test_original_case_resolution_does_not_cross_categories(self):
        annotation = (
            self.db.query(models.DisinfectionAnnotation)
            .filter(models.DisinfectionAnnotation.source_sha256 == "sha-0")
            .one()
        )
        annotation.product_category = "消毒柜"
        annotation.original_image_path = str(self.uploads / "case.png")
        wrong_image = models.Image(
            url="/uploads/case.png",
            filename="case.png",
            source_type="company_published",
        )
        self.db.add(wrong_image)
        self.db.flush()
        self.db.add(models.Case(
            image_id=wrong_image.id,
            name="wrong",
            product_category="奶瓶",
        ))
        self.db.commit()
        with patch("app.main.config.UPLOAD_DIR", self.uploads):
            matched = _find_annotation_original_case(self.db, annotation)
        self.assertEqual(self.case.id, matched.id)

    def test_finalize_preserves_initial_ai_snapshot(self):
        initial = {"version": 1, "modules_json": [{"id": "ai"}]}
        blueprint = models.LayoutBlueprint(
            case_id=self.case.id,
            version=3,
            review_status="verified",
            modules_json="[]",
            margins="{}",
            margins_json="{}",
        )
        self.db.add(blueprint)
        self.db.flush()
        run = models.DisinfectionDecompositionRun(
            case_id=self.case.id,
            blueprint_id=blueprint.id,
            status="review_required",
            initial_ai_blueprint_json=json.dumps(initial),
        )
        self.db.add(run)
        self.db.commit()
        result = finalize_disinfection_decomposition_run(
            run.id, {"blueprint_id": blueprint.id}, self.db
        )
        self.assertEqual(initial, result["initial_ai_blueprint"])
        self.assertEqual("verified", result["status"])
        self.assertEqual(2, result["manual_edit_count"])

    def test_manual_annotation_edit_creates_history_and_keeps_initial(self):
        annotation = (
            self.db.query(models.DisinfectionAnnotation)
            .filter(models.DisinfectionAnnotation.source_sha256 == "sha-0")
            .one()
        )
        initial = annotation.regions_json
        result = update_disinfection_annotation(
            annotation.id,
            {
                "regions": [{
                    "id": "manual", "type": "main_text", "color": "green",
                    "x": .2, "y": .1, "width": .5, "height": .1,
                    "confidence": 1,
                }],
                "reviewer": "设计负责人",
                "project_key": "project-a",
            },
            self.db,
        )
        self.assertEqual(2, result["annotation_version"])
        history = (
            self.db.query(models.DisinfectionAnnotationVersion)
            .filter(models.DisinfectionAnnotationVersion.annotation_id == annotation.id)
            .one()
        )
        self.assertEqual(initial, json.dumps(json.loads(history.payload_json)["regions"], ensure_ascii=False))

    def test_accurate_but_not_recommended_can_be_verified(self):
        regions = [
            {"id": "layout", "type": "layout_block", "x": .05, "y": .05, "width": .9, "height": .9},
            {"id": "product", "type": "product_image", "x": .1, "y": .25, "width": .4, "height": .4},
            {"id": "text", "type": "main_text", "x": .1, "y": .1, "width": .6, "height": .1},
        ]
        row = models.DisinfectionAnnotation(
            source_sha256="accurate-negative", source_type="company_published",
            status="pending_review", product_category="吸奶器",
            project_key="历史项目待补充", page_role="other",
            original_image_path=str(self.uploads / "case.png"),
            regions_json=json.dumps(regions),
        )
        self.db.add(row); self.db.commit()
        set_disinfection_annotation_recommendation(row.id, {
            "decision": "not_recommended", "reviewer": "设计负责人",
            "not_recommended_reason": "信息层级混乱",
            "avoid_reasons": ["标题过小"], "keep_reasons": ["产品图清晰"],
        }, self.db)
        result = verify_disinfection_annotation(row.id, {
            "reviewer": "设计负责人", "pairing_confirmed": True,
            "boxes_confirmed": True, "page_role_confirmed": True,
            "reading_order": ["layout", "text", "product"],
        }, self.db)
        self.assertTrue(result["annotation_verified"])
        self.assertFalse(result["company_recommended"])
        self.assertEqual("历史项目待补充", self.db.get(models.DisinfectionAnnotation, row.id).project_key)

    def test_needs_box_fix_cannot_be_verified(self):
        row = models.DisinfectionAnnotation(
            source_sha256="missing-boxes", source_type="company_published",
            status="pending_review", product_category="吸奶器",
            project_key="历史项目待补充", page_role="other",
            original_image_path=str(self.uploads / "case.png"),
            regions_json=json.dumps([{"id": "product", "type": "product_image", "x": .1, "y": .2, "width": .5, "height": .5}]),
        )
        self.db.add(row); self.db.commit()
        with self.assertRaises(HTTPException) as error:
            verify_disinfection_annotation(row.id, {
                "reviewer": "设计负责人", "pairing_confirmed": True,
                "boxes_confirmed": True, "page_role_confirmed": True,
                "reading_order": ["product"],
            }, self.db)
        self.assertIn("needs_box_fix", str(error.exception.detail))

    def test_external_reference_cannot_be_company_recommended(self):
        row = models.DisinfectionAnnotation(
            source_sha256="external-reference", source_type="external_reference",
            status="verified", product_category="吸奶器",
        )
        self.db.add(row); self.db.commit()
        with self.assertRaises(HTTPException):
            set_disinfection_annotation_recommendation(row.id, {
                "decision": "recommended", "reviewer": "设计负责人",
                "lead_confirmed": True,
            }, self.db)


if __name__ == "__main__":
    unittest.main()
