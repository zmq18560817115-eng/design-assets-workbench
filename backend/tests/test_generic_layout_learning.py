from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.disinfection_annotations import (
    select_few_shot_annotations,
    verified_statistics,
)
from app.schemas import LayoutAnnotationPayload


def row(
    identifier: int,
    category: str,
    source_type: str = "company_published",
    status: str = "verified",
):
    return SimpleNamespace(
        id=identifier,
        status=status,
        source_type=source_type,
        dataset_split="calibration",
        product_category=category,
        orientation="portrait",
        page_role="product_display",
        canvas_width=900,
        canvas_height=1200,
        regions_json="[]",
    )


class GenericLayoutLearningTests(unittest.TestCase):
    def test_exact_category_company_evidence_is_prioritized(self):
        rows = [row(1, "消毒柜"), row(2, "奶瓶"), row(3, "吸奶器")]
        selected = select_few_shot_annotations(
            rows,
            product_category="奶瓶",
            orientation="portrait",
        )
        self.assertEqual(2, selected[0].id)

    def test_external_reference_requires_explicit_imitation_mode(self):
        rows = [
            row(1, "奶瓶", "external_reference"),
            row(2, "吸奶器", "company_published"),
        ]
        company = select_few_shot_annotations(
            rows, product_category="奶瓶", orientation="portrait"
        )
        imitation = select_few_shot_annotations(
            rows,
            product_category="奶瓶",
            orientation="portrait",
            evidence_mode="imitation",
        )
        self.assertEqual([2], [item.id for item in company])
        self.assertEqual([2, 1], [item.id for item in imitation])

    def test_rejected_design_never_enters_evidence(self):
        selected = select_few_shot_annotations(
            [row(1, "奶瓶", "rejected_company_design")],
            product_category="奶瓶",
            orientation="portrait",
            evidence_mode="imitation",
        )
        self.assertEqual([], selected)

    def test_readiness_is_per_category_and_requires_thirty(self):
        rows = [row(index, "奶瓶") for index in range(1, 7)]
        stats = verified_statistics(rows, product_category="奶瓶")
        self.assertEqual("not_ready", stats["status"])
        self.assertEqual(24, stats["remaining_to_ready"])

    def test_schema_accepts_other_categories_but_rejects_unknown_source(self):
        base = {
            "image_path": "sample.png",
            "product_category": "吸奶器",
            "canvas_width": 900,
            "canvas_height": 1200,
            "canvas_ratio": "3:4",
            "orientation": "portrait",
            "created_at": "2026-07-31T00:00:00Z",
        }
        self.assertEqual("吸奶器", LayoutAnnotationPayload(**base).product_category)
        with self.assertRaises(ValueError):
            LayoutAnnotationPayload(**base, source_type="unknown")


if __name__ == "__main__":
    unittest.main()
