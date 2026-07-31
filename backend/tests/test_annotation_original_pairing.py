from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from scripts.pair_layout_annotation_originals import pair


class AnnotationOriginalPairingTests(unittest.TestCase):
    def test_colored_boxes_do_not_hide_correct_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.png"
            distractor = root / "distractor.png"
            annotated = root / "annotated.png"

            artwork = Image.new("RGB", (300, 400), "white")
            draw = ImageDraw.Draw(artwork)
            draw.rectangle((40, 80, 260, 330), fill="#d8e8ff")
            draw.ellipse((90, 130, 210, 270), fill="#667799")
            artwork.save(original)
            Image.new("RGB", (300, 400), "#f2c6a0").save(distractor)

            boxed = artwork.copy()
            box_draw = ImageDraw.Draw(boxed)
            box_draw.rectangle((20, 30, 280, 360), outline="#ff0000", width=8)
            box_draw.rectangle((70, 110, 230, 290), outline="#1687ff", width=8)
            box_draw.rectangle((40, 45, 240, 75), outline="#2fad38", width=8)
            boxed.save(annotated)

            row = SimpleNamespace(id=1, annotated_image_path=str(annotated))
            result = pair([row], [distractor, original])[0]
            self.assertEqual(original.resolve(), Path(result["original_path"]))
            self.assertEqual("high_confidence", result["pairing_status"])


if __name__ == "__main__":
    unittest.main()
