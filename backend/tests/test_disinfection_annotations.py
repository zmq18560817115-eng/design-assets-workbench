import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from app.disinfection_annotations import (
    annotation_is_verified,
    assign_dataset_splits,
    eligible_for_company_pattern,
    evaluate_regions,
    parse_colored_rectangles,
    scan_directory,
    select_few_shot_annotations,
    verified_statistics,
)


class DisinfectionAnnotationParserTests(unittest.TestCase):
    def test_detects_three_annotation_colors_and_normalizes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.png"
            image = Image.new("RGB", (400, 600), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 30, 380, 200), outline=(255, 0, 0), width=6)
            draw.rectangle((50, 240, 180, 430), outline=(0, 140, 255), width=6)
            draw.rectangle((210, 240, 360, 310), outline=(47, 173, 22), width=6)
            image.save(path)
            regions, warnings = parse_colored_rectangles(path)
            self.assertEqual({"layout_block", "product_image", "main_text"}, {r["type"] for r in regions})
            self.assertFalse(warnings)
            self.assertTrue(all(0 <= r[k] <= 1 for r in regions for k in ("x", "y", "width", "height")))

    def test_no_fake_fallback_regions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plain.png"
            Image.new("RGB", (300, 500), "white").save(path)
            regions, warnings = parse_colored_rectangles(path)
            self.assertEqual([], regions)
            self.assertEqual(3, len(warnings))

    def test_scan_is_read_only_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new("RGB", (100, 200), "white").save(root / "a.png")
            before = (root / "a.png").read_bytes()
            report = scan_directory(root)
            self.assertEqual(1, report["total"])
            self.assertEqual({"portrait": 1}, report["orientations"])
            self.assertEqual(before, (root / "a.png").read_bytes())
            json.dumps(report)

    def test_broken_box_is_reported_without_fake_region(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.png"
            image = Image.new("RGB", (400, 600), "white")
            draw = ImageDraw.Draw(image)
            draw.line((20, 30, 380, 30), fill=(255, 0, 0), width=6)
            draw.line((20, 30, 20, 200), fill=(255, 0, 0), width=6)
            image.save(path)
            regions, warnings = parse_colored_rectangles(path)
            self.assertFalse(any(r["type"] == "layout_block" for r in regions))
            self.assertIn("broken_or_missing_red_rectangle", warnings)

    def test_only_verified_company_calibration_enters_few_shot(self):
        base = dict(
            orientation="portrait", page_role="product_display",
            canvas_width=900, canvas_height=1200,
            annotation_verified=True, company_recommended=True,
            recommendation_confirmed_by_lead=True,
        )
        rows = [
            SimpleNamespace(id=1, status="verified", source_type="company_published", dataset_split="calibration", **base),
            SimpleNamespace(id=2, status="pending_review", source_type="company_published", dataset_split="calibration", **base),
            SimpleNamespace(id=3, status="verified", source_type="external_reference", dataset_split="calibration", **base),
            SimpleNamespace(id=4, status="verified", source_type="rejected_company_design", dataset_split="calibration", **base),
            SimpleNamespace(id=5, status="verified", source_type="company_published", dataset_split="holdout", **base),
        ]
        self.assertEqual(
            [1],
            [row.id for row in select_few_shot_annotations(rows, orientation="portrait")],
        )

    def test_annotation_accuracy_and_company_recommendation_are_independent(self):
        accurate_negative = SimpleNamespace(
            status="verified", annotation_verified=True,
            source_type="company_published", company_recommended=False,
            recommendation_confirmed_by_lead=True,
        )
        recommended_unverified = SimpleNamespace(
            status="pending_review", annotation_verified=False,
            source_type="company_published", company_recommended=True,
            recommendation_confirmed_by_lead=True,
        )
        complete_positive = SimpleNamespace(
            status="verified", annotation_verified=True,
            source_type="company_published", company_recommended=True,
            recommendation_confirmed_by_lead=True,
        )
        self.assertTrue(annotation_is_verified(accurate_negative))
        self.assertFalse(eligible_for_company_pattern(accurate_negative))
        self.assertFalse(eligible_for_company_pattern(recommended_unverified))
        self.assertTrue(eligible_for_company_pattern(complete_positive))

    def test_external_reference_never_enters_company_pattern(self):
        row = SimpleNamespace(
            status="verified", annotation_verified=True,
            source_type="external_reference", company_recommended=True,
            recommendation_confirmed_by_lead=True,
        )
        self.assertFalse(eligible_for_company_pattern(row))

    def test_unverified_is_excluded_from_statistics(self):
        region = json.dumps([{
            "id": "r", "type": "product_image", "x": 0.1, "y": 0.1,
            "width": 0.5, "height": 0.5,
        }])
        row = SimpleNamespace(
            id=1, status="pending_review", source_type="company_published",
            regions_json=region, canvas_width=900, canvas_height=1200,
            orientation="portrait", page_role="other",
        )
        self.assertEqual("not_ready", verified_statistics([row])["status"])

    def test_project_group_never_crosses_splits(self):
        rows = [
            SimpleNamespace(id=1, project_key="project-a"),
            SimpleNamespace(id=2, project_key="project-a"),
            SimpleNamespace(id=3, project_key="project-b"),
            SimpleNamespace(id=4, project_key="project-c"),
            SimpleNamespace(id=5, project_key="project-d"),
        ]
        split = assign_dataset_splits(rows)
        self.assertEqual(split[1], split[2])
        self.assertIn("holdout", set(split.values()))
        self.assertIn("calibration", set(split.values()))

    def test_holdout_metrics_report_illegal_coordinates(self):
        truth = [{"type": "product_image", "x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4}]
        predicted = [{"type": "product_image", "x": 0.8, "y": 0.1, "width": 0.4, "height": 0.4}]
        metrics = evaluate_regions(predicted, truth)
        self.assertEqual(1, metrics["out_of_bounds"])
        self.assertEqual(0, metrics["coordinate_validity"])


if __name__ == "__main__":
    unittest.main()
