from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models
from app.database import Base
from app.schemas import CaseReviewInput


class ReviewPatchSemanticsTest(unittest.TestCase):
    def test_blank_review_fields_do_not_erase_business_metadata(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        image = models.Image(url="/a.png", filename="a.png")
        db.add(image)
        db.flush()
        case = models.Case(
            image_id=image.id, name="sample", product_name="消毒柜 A",
            content_purpose="产品卖点", page_role="product_display",
            sequence_index=3, brief_ref="BRIEF-001",
        )
        db.add(case)
        db.flush()
        case.analysis = models.Analysis(case_id=case.id)
        db.commit()
        review = CaseReviewInput(
            reviewer="设计负责人",
            product_name="", content_purpose="", brief_ref="",
            trust_status="verified",
        )
        crud.review_case(db, case, review)
        self.assertEqual(case.product_name, "消毒柜 A")
        self.assertEqual(case.content_purpose, "产品卖点")
        self.assertEqual(case.page_role, "product_display")
        self.assertEqual(case.sequence_index, 3)
        self.assertEqual(case.brief_ref, "BRIEF-001")
        db.close()


if __name__ == "__main__":
    unittest.main()
