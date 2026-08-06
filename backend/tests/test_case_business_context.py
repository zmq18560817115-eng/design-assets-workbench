from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_business_context as service, models
from app.database import Base


class CaseBusinessContextTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        project = models.Project(name="P", description="", business_line="", status="active", is_gold=False)
        self.db.add(project); self.db.flush()
        self.blueprints = {}
        for case_id in (100, 228, 923):
            image = models.Image(url=f"/uploads/{case_id}.png", filename=f"{case_id}.png", source_type="company_published")
            self.db.add(image); self.db.flush()
            case = models.Case(id=case_id, image_id=image.id, project_id=project.id, name=f"C{case_id}", product_category="羊脂膏", scene="AI scene", content_purpose="AI purpose", page_role="other", trust_status="verified")
            self.db.add(case); self.db.flush()
            blueprint = models.LayoutBlueprint(case_id=case_id, canvas_ratio="1:1", orientation="square", module_count=1, modules_json=json.dumps([{"id":"p","type":"product_image","x":0.1,"y":0.1,"width":0.5,"height":0.5,"priority":1,"importance":1,"alignment":"center","description":"","label":"","content_summary":"","confidence":1}]), review_status="verified", version=1)
            self.db.add(blueprint); self.db.flush(); self.blueprints[case_id] = blueprint
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_initialize_is_scoped_draft_and_idempotent(self):
        scoped = {100: self.blueprints[100], 923: self.blueprints[923]}
        with patch.object(service, "target_blueprints", return_value=scoped):
            first = service.initialize_contexts(self.db)
            second = service.initialize_contexts(self.db)
        self.assertEqual(first["created_count"], 2)
        self.assertEqual(second["created_count"], 0)
        self.assertIsNone(self.db.query(models.CaseBusinessContext).filter_by(case_id=228).first())
        weak = self.db.query(models.CaseBusinessContext).filter_by(case_id=923).one()
        self.assertEqual(weak.evidence_strength, "weak")
        self.assertEqual(weak.confirmation_status, "draft")
        self.assertIsNone(weak.content_purpose)
        self.assertEqual(json.loads(weak.suggestion_json)["content_purpose"]["status"], "ai_suggested")
        self.assertEqual(self.db.query(models.CaseBusinessContextEvent).count(), 2)

    def test_unknown_and_ai_suggestion_cannot_verify(self):
        with patch.object(service, "target_blueprints", return_value={100: self.blueprints[100]}):
            service.initialize_contexts(self.db)
        with self.assertRaisesRegex(service.ContextValidationError, "content_purpose"):
            service.update_contexts(self.db, [100], {}, "Owner", verify=True)
        row = self.db.query(models.CaseBusinessContext).filter_by(case_id=100).one()
        self.assertEqual(row.confirmation_status, "draft")

    def test_batch_requires_reviewer_and_appends_history(self):
        with patch.object(service, "target_blueprints", return_value={100: self.blueprints[100]}):
            service.initialize_contexts(self.db)
        with self.assertRaisesRegex(service.ContextValidationError, "审核人"):
            service.update_contexts(self.db, [100], {"channel": "ecommerce"}, "")
        result = service.update_contexts(self.db, [100], {
            "content_purpose": "selling-point", "channel": "ecommerce", "page_role": "detail",
        }, "Owner", verify=True)
        self.assertEqual(result[0]["confirmation_status"], "verified")
        self.assertEqual(self.db.query(models.CaseBusinessContextEvent).count(), 2)


if __name__ == "__main__":
    unittest.main()
