import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.disinfection_annotations import parse_colored_rectangles, scan_directory


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


if __name__ == "__main__":
    unittest.main()
