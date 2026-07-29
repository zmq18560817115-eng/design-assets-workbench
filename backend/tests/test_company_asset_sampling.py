from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.sampling import color_sample, color_score
from app.vlm import _model_image_payload


class CompanyAssetSamplingTest(unittest.TestCase):
    def test_model_payload_is_bounded_for_large_images(self) -> None:
        image = Image.new("RGB", (3200, 2400), "#F23869")
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            image.save(handle, format="PNG")
            handle.seek(0)
            original = handle.read()
        prepared, mime = _model_image_payload(original, "image/png")
        self.assertEqual(mime, "image/jpeg")
        self.assertLess(len(prepared), len(original))
        with Image.open(__import__("io").BytesIO(prepared)) as result:
            self.assertLessEqual(max(result.size), 1600)

    def test_color_sampling_prefers_color_rich_diverse_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="color-sampling-") as tmp:
            root = Path(tmp)
            gray = Image.new("RGB", (240, 240), "#B8B8B8")
            gray_path = root / "gray.png"
            gray.save(gray_path)

            colorful = Image.new("RGB", (240, 240), "#F23869")
            draw = ImageDraw.Draw(colorful)
            draw.rectangle((80, 0, 159, 239), fill="#16A7E0")
            draw.rectangle((160, 0, 239, 239), fill="#F5C542")
            colorful_path = root / "colorful.png"
            colorful.save(colorful_path)

            duplicate_path = root / "colorful-copy.png"
            colorful.save(duplicate_path)

            self.assertGreater(
                color_score(colorful_path),
                color_score(gray_path),
            )
            selected = color_sample(
                [gray_path, colorful_path, duplicate_path],
                2,
            )
            selected_paths = [path for path, _ in selected]
            self.assertEqual(
                sum(
                    path in {colorful_path, duplicate_path}
                    for path in selected_paths
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
