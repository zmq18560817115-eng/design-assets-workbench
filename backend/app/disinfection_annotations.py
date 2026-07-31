"""Parse and report human colored-box annotations without inventing regions."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

COLOR_TYPES = {
    "red": "layout_block",
    "blue": "product_image",
    "green": "main_text",
}


def _is_color(pixel: tuple[int, ...], color: str) -> bool:
    r, g, b = pixel[:3]
    if color == "red":
        # The annotation export uses near-exact saturated strokes. Tight
        # palettes deliberately avoid red products, skin and promotional art.
        return r >= 235 and g <= 40 and b <= 40
    if color == "blue":
        return r <= 45 and 95 <= g <= 185 and b >= 220
    return 15 <= r <= 85 and 125 <= g <= 215 and b <= 75


def _runs(bits: list[bool], minimum: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for index, on in enumerate(bits + [False]):
        if on and start is None:
            start = index
        elif not on and start is not None:
            if index - start >= minimum:
                out.append((start, index - 1))
            start = None
    return out


def _bands(image: Image.Image, color: str) -> list[dict[str, int]]:
    width, height = image.size
    pixels = image.load()
    minimum = max(18, int(width * 0.025))
    lines: list[tuple[int, int, int]] = []
    for y in range(height):
        bits = [_is_color(pixels[x, y], color) for x in range(width)]
        lines.extend((y, x1, x2) for x1, x2 in _runs(bits, minimum))
    bands: list[dict[str, int]] = []
    tolerance = max(4, int(width * 0.008))
    for y, x1, x2 in lines:
        match = next(
            (
                band for band in reversed(bands[-30:])
                if y <= band["y2"] + 2
                and abs(x1 - band["x1"]) <= tolerance
                and abs(x2 - band["x2"]) <= tolerance
            ),
            None,
        )
        if match:
            match["y2"] = y
            match["x1"] = min(match["x1"], x1)
            match["x2"] = max(match["x2"], x2)
        else:
            bands.append({"x1": x1, "x2": x2, "y1": y, "y2": y})
    return bands


def _vertical_coverage(
    image: Image.Image, color: str, x: int, y1: int, y2: int
) -> float:
    pixels = image.load()
    width, _ = image.size
    radius = max(2, int(width * 0.004))
    hits = 0
    total = max(1, y2 - y1 + 1)
    for y in range(y1, y2 + 1):
        if any(_is_color(pixels[cx, y], color) for cx in range(max(0, x-radius), min(width, x+radius+1))):
            hits += 1
    return hits / total


def _iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    inter = max(0, min(ax2, bx2) - max(a["x"], b["x"])) * max(
        0, min(ay2, by2) - max(a["y"], b["y"])
    )
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0


def parse_colored_rectangles(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    regions: list[dict[str, Any]] = []
    warnings: list[str] = []
    for color, region_type in COLOR_TYPES.items():
        bands = _bands(image, color)
        tolerance = max(8, int(width * 0.018))
        found = 0
        for top_index, top in enumerate(bands):
            for bottom in bands[top_index + 1:]:
                if bottom["y1"] - top["y2"] < max(15, int(height * 0.015)):
                    continue
                if abs(top["x1"] - bottom["x1"]) > tolerance or abs(top["x2"] - bottom["x2"]) > tolerance:
                    continue
                x1 = round((top["x1"] + bottom["x1"]) / 2)
                x2 = round((top["x2"] + bottom["x2"]) / 2)
                left = _vertical_coverage(image, color, x1, top["y1"], bottom["y2"])
                right = _vertical_coverage(image, color, x2, top["y1"], bottom["y2"])
                confidence = (left + right) / 2
                if confidence < 0.62:
                    continue
                item = {
                    "id": f"{color}-{found + 1}",
                    "type": region_type,
                    "color": color,
                    "x": round(x1 / width, 6),
                    "y": round(top["y1"] / height, 6),
                    "width": round(max(1, x2 - x1) / width, 6),
                    "height": round(max(1, bottom["y2"] - top["y1"]) / height, 6),
                    "confidence": round(confidence, 3),
                    "annotation_source": "color_box_parser_v1",
                }
                if item["width"] < 0.025 or item["height"] < 0.018:
                    continue
                if any(existing["color"] == color and _iou(existing, item) > 0.88 for existing in regions):
                    continue
                regions.append(item)
                found += 1
                break
        if not found:
            warnings.append(f"no_closed_{color}_rectangle")
    regions.sort(key=lambda item: (item["y"], item["x"], item["type"]))
    for index, region in enumerate(regions, 1):
        region["id"] = f"region-{index}"
    return regions, warnings


def scan_directory(root: Path) -> dict[str, Any]:
    files = sorted(
        (p for p in root.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}),
        key=lambda p: p.name.lower(),
    )
    items = []
    sizes: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    orientations: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for path in files:
        with Image.open(path) as image:
            width, height = image.size
            fmt = image.format or path.suffix.lstrip(".").upper()
        orientation = "portrait" if height > width else "landscape" if width > height else "square"
        regions, warnings = parse_colored_rectangles(path)
        counts = Counter(item["type"] for item in regions)
        totals.update(counts)
        sizes[f"{width}x{height}"] += 1
        formats[fmt] += 1
        orientations[orientation] += 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append({
            "relative_path": path.name,
            "sha256": digest,
            "width": width,
            "height": height,
            "orientation": orientation,
            "regions": regions,
            "region_counts": dict(counts),
            "warnings": ["unannotated_original_not_found", *warnings],
            "pairing_status": "annotated_only",
        })
    return {
        "source_root": str(root),
        "total": len(items),
        "formats": dict(formats),
        "sizes": dict(sizes),
        "orientations": dict(orientations),
        "region_totals": dict(totals),
        "pairing": {"annotated_only": len(items), "paired": 0},
        "items": items,
    }


def write_scan_report(root: Path, output: Path) -> dict[str, Any]:
    report = scan_directory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
