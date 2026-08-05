from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.formal_pattern_evidence_verification import (
    AUTH_REASON,
    AUTH_STATUS,
    REVIEWER,
    FormalEvidenceVerificationError,
    _add_product_from_annotation,
    _annotation_blueprint,
    _blueprint_payload,
    _modules_from_annotation,
    _new_blueprint,
)


class FormalPatternEvidenceVerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        image = models.Image(url="/uploads/a.png", filename="a.png", source_type="company_published")
        self.db.add(image); self.db.flush()
        self.case = models.Case(image_id=image.id, name="a", product_category="羊脂膏")
        self.db.add(self.case); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.temp.cleanup()

    @staticmethod
    def annotation(*, product=True):
        regions = [
            {"id": "layout", "type": "layout_block", "x": .05, "y": .05, "width": .9, "height": .9, "confidence": 1},
            {"id": "text", "type": "main_text", "x": .1, "y": .1, "width": .5, "height": .1, "confidence": 1},
        ]
        if product:
            regions.append({"id": "product", "type": "product_image", "x": .2, "y": .3, "width": .4, "height": .5, "confidence": 1})
        return models.DisinfectionAnnotation(
            id=224, source_sha256="sha", product_category="羊脂膏",
            canvas_width=1000, canvas_height=1000, orientation="square",
            regions_json=json.dumps(regions),
        )

    def blueprint(self, modules):
        return models.LayoutBlueprint(
            id=1, case_id=self.case.id, canvas_ratio="1:1", orientation="square",
            grid_columns=6, grid_rows=12, margins="{}", margins_json="{}",
            alignment="mixed", reading_flow="top-to-bottom", focal_region="",
            information_density="medium", text_image_ratio=.5,
            module_count=len(modules), modules_json=json.dumps(modules),
            review_status="ai_generated", model_name="legacy", prompt_version="v1",
        )

    def test_legacy_types_have_explicit_mapping_without_geometry_change(self):
        modules = [
            {"id": "a", "type": "title", "x": .1, "y": .1, "width": .3, "height": .1},
            {"id": "b", "type": "supporting_text", "x": .1, "y": .3, "width": .3, "height": .1},
        ]
        payload = _blueprint_payload(self.blueprint(modules), status="corrected", editor=REVIEWER)
        self.assertEqual([item.type for item in payload.modules_json], ["main_title", "body_text"])
        self.assertEqual(payload.modules_json[0].x, modules[0]["x"])
        self.assertEqual(len(payload.modules_json), len(modules))

    def test_product_module_comes_only_from_existing_blue_region(self):
        current = self.blueprint([{"id": "text", "type": "main_title", "x": .1, "y": .1, "width": .3, "height": .1}])
        payload = _add_product_from_annotation(current, self.annotation(product=True))
        product = next(item for item in payload.modules_json if item.type == "product_image")
        self.assertEqual((product.x, product.y, product.width, product.height), (.2, .3, .4, .5))

    def test_missing_product_region_is_blocked(self):
        current = self.blueprint([{"id": "text", "type": "main_title", "x": .1, "y": .1, "width": .3, "height": .1}])
        with self.assertRaisesRegex(FormalEvidenceVerificationError, "annotation_product_region_missing"):
            _add_product_from_annotation(current, self.annotation(product=False))

    def test_case_923_blueprint_uses_only_annotation_regions(self):
        annotation = self.annotation(product=True)
        payload = _annotation_blueprint(annotation)
        source = json.loads(annotation.regions_json)
        self.assertEqual(len(payload.modules_json), len(source))
        self.assertEqual(
            {(item.x, item.y, item.width, item.height) for item in payload.modules_json},
            {(item["x"], item["y"], item["width"], item["height"]) for item in source},
        )

    def test_case_923_invalid_annotation_is_blocked(self):
        with self.assertRaisesRegex(FormalEvidenceVerificationError, "annotation_required_regions_missing"):
            _annotation_blueprint(self.annotation(product=False))

    def test_new_blueprint_preserves_versions(self):
        current = self.blueprint([{"id": "text", "type": "main_title", "x": .1, "y": .1, "width": .3, "height": .1}])
        current.id = None; current.version = 1
        self.db.add(current); self.db.flush()
        payload = _blueprint_payload(current, status="verified", editor=REVIEWER)
        revised = _new_blueprint(self.db, self.case.id, payload)
        self.assertEqual(revised.version, 2)
        self.assertEqual(self.db.query(models.LayoutBlueprint).filter_by(case_id=self.case.id).count(), 2)

    def test_authorization_keeps_detection_source_transparent(self):
        annotation = self.annotation(); annotation.id = None
        self.db.add(annotation); self.db.flush()
        event = models.PairingAuthorizationEvent(
            annotation_id=annotation.id,
            pairing_detection_source="automatic_exact_match",
            authorization_status=AUTH_STATUS, authorized_by=REVIEWER,
            authorization_reason=AUTH_REASON,
        )
        self.db.add(event); self.db.commit()
        self.assertEqual(event.pairing_detection_source, "automatic_exact_match")
        self.assertNotEqual(event.pairing_detection_source, "human_confirmed")

    def test_authorization_event_is_idempotent(self):
        annotation = self.annotation(); annotation.id = None
        self.db.add(annotation); self.db.flush()
        values = dict(annotation_id=annotation.id, pairing_detection_source="automatic_exact_match",
                      authorization_status=AUTH_STATUS, authorized_by=REVIEWER, authorization_reason=AUTH_REASON)
        self.db.add(models.PairingAuthorizationEvent(**values)); self.db.commit()
        self.db.add(models.PairingAuthorizationEvent(**values))
        with self.assertRaises(IntegrityError): self.db.commit()
        self.db.rollback()

    def test_verified_event_records_source_pattern_and_reviewer(self):
        blueprint = self.blueprint([{"id": "text", "type": "main_title", "x": .1, "y": .1, "width": .3, "height": .1}])
        blueprint.id = None; blueprint.version = 1
        self.db.add(blueprint); self.db.flush()
        event = models.LayoutBlueprintVerificationEvent(
            blueprint_id=blueprint.id, case_id=self.case.id,
            source_pattern_ids_json="[7]", reviewer=REVIEWER,
            verification_source="owner_authorized_verified_pattern_evidence",
        )
        self.db.add(event); self.db.commit()
        self.assertEqual(json.loads(event.source_pattern_ids_json), [7])
        self.assertEqual(event.reviewer, REVIEWER)

    def test_annotation_module_reading_order_is_unique_and_complete(self):
        modules = _modules_from_annotation(self.annotation())
        self.assertEqual([item["priority"] for item in modules], list(range(1, len(modules) + 1)))


if __name__ == "__main__":
    unittest.main()
