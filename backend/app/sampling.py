"""Pure image-sampling helpers with no database or application side effects."""
from __future__ import annotations

import colorsys
import math
from pathlib import Path

from PIL import Image

from . import imagehash


def hash_int(path: Path) -> int | None:
    try:
        return int(imagehash.dhash(str(path)), 16)
    except Exception:
        return None


def hash_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def color_score(path: Path) -> float:
    """Score how useful an image is for learning an intentional color system."""
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((128, 128))
            pixels = list(image.getdata())
    except Exception:
        return -1.0
    if not pixels:
        return -1.0

    saturations: list[float] = []
    rg_values: list[float] = []
    yb_values: list[float] = []
    for red, green, blue in pixels:
        _, saturation, _ = colorsys.rgb_to_hsv(
            red / 255,
            green / 255,
            blue / 255,
        )
        saturations.append(saturation)
        rg_values.append(red - green)
        yb_values.append((red + green) / 2 - blue)

    def mean(values: list[float]) -> float:
        return sum(values) / len(values)

    def std(values: list[float], average: float) -> float:
        return math.sqrt(
            sum((value - average) ** 2 for value in values) / len(values)
        )

    saturation_mean = mean(saturations)
    saturation_p75 = sorted(saturations)[
        round((len(saturations) - 1) * 0.75)
    ]
    rg_mean = mean(rg_values)
    yb_mean = mean(yb_values)
    colorfulness = math.sqrt(
        std(rg_values, rg_mean) ** 2 + std(yb_values, yb_mean) ** 2
    ) + 0.3 * math.sqrt(rg_mean**2 + yb_mean**2)

    quantized = image.quantize(colors=8)
    counts = quantized.getcolors() or []
    total = sum(count for count, _ in counts) or 1
    entropy = -sum(
        (count / total) * math.log2(count / total)
        for count, _ in counts
        if count
    )
    return round(
        saturation_mean * 45
        + saturation_p75 * 25
        + min(colorfulness / 100, 1) * 20
        + min(entropy / 3, 1) * 10,
        2,
    )


def color_sample(paths: list[Path], limit: int) -> list[tuple[Path, float]]:
    """Choose high-scoring color candidates and remove near-identical exports."""
    ranked = sorted(
        ((path, color_score(path), hash_int(path)) for path in paths),
        key=lambda item: (-item[1], str(item[0])),
    )
    chosen: list[tuple[Path, float, int | None]] = []
    for item in ranked:
        if item[1] < 0:
            continue
        if item[2] is not None and any(
            selected[2] is not None
            and hash_distance(item[2], selected[2]) < 8
            for selected in chosen
        ):
            continue
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return [(path, score) for path, score, _ in chosen]
