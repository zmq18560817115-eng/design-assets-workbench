"""Parse and report human colored-box annotations without inventing regions."""
from __future__ import annotations

import hashlib
import json
import math
import datetime as dt
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
                    warnings.append(f"too_small_{color}_rectangle")
                    continue
                if any(existing["color"] == color and _iou(existing, item) > 0.88 for existing in regions):
                    warnings.append(f"duplicate_{color}_rectangle_edge")
                    continue
                regions.append(item)
                found += 1
                break
        if not found:
            warnings.append(
                f"broken_or_missing_{color}_rectangle" if bands
                else f"no_{color}_rectangle"
            )
    regions.sort(key=lambda item: (item["y"], item["x"], item["type"]))
    for index, region in enumerate(regions, 1):
        region["id"] = f"region-{index}"
    for index, left in enumerate(regions):
        for right in regions[index + 1:]:
            overlap = _iou(left, right)
            if overlap >= 0.75:
                warnings.append(
                    f"heavy_overlap:{left['id']}:{right['id']}:{overlap:.2f}"
                )
    return regions, warnings


def canvas_ratio(width: int, height: int) -> str:
    divisor = math.gcd(max(1, width), max(1, height))
    return f"{width // divisor}:{height // divisor}"


def annotation_payload(item: dict[str, Any]) -> dict[str, Any]:
    """Return the stable, per-image contract consumed by review tooling."""
    return {
        "image_path": item["relative_path"],
        "product_category": "消毒柜",
        "source_type": "company_published",
        "annotation_source": "human_color_box_v1",
        "annotation_status": "pending_review",
        "canvas_width": item["width"],
        "canvas_height": item["height"],
        "canvas_ratio": canvas_ratio(item["width"], item["height"]),
        "orientation": item["orientation"],
        "regions": [
            {
                "id": region["id"],
                "color": region["color"],
                "semantic_type": region["type"],
                "x": region["x"],
                "y": region["y"],
                "width": region["width"],
                "height": region["height"],
                "confidence": region["confidence"],
            }
            for region in item["regions"]
        ],
        "detection_warnings": item["warnings"],
        "annotation_version": 1,
        "created_at": item["annotation_created_at"],
        "reviewer": "",
        "history": [
            {
                "version": 1,
                "source": "color_box_parser_v1",
                "status": "pending_review",
                "created_at": item["annotation_created_at"],
            }
        ],
    }


def scan_directory(root: Path) -> dict[str, Any]:
    annotation_created_at = dt.datetime.now(dt.UTC).isoformat()
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
            "source_modified_at": dt.datetime.fromtimestamp(
                path.stat().st_mtime, tz=dt.UTC
            ).isoformat(),
            "annotation_created_at": annotation_created_at,
        })
    return {
        "source_root": root.name,
        "scan_created_at": annotation_created_at,
        "total": len(items),
        "formats": dict(formats),
        "sizes": dict(sizes),
        "orientations": dict(orientations),
        "region_totals": dict(totals),
        "box_detection_success": {
            kind: sum(item["region_counts"].get(kind, 0) > 0 for item in items)
            for kind in COLOR_TYPES.values()
        },
        "pairing": {"annotated_only": len(items), "paired": 0},
        "ambiguous_items": [
            {
                "relative_path": item["relative_path"],
                "warnings": [
                    warning for warning in item["warnings"]
                    if warning != "unannotated_original_not_found"
                ],
            }
            for item in items
            if any(
                warning != "unannotated_original_not_found"
                for warning in item["warnings"]
            )
        ],
        "items": items,
    }


def write_scan_report(root: Path, output: Path) -> dict[str, Any]:
    report = scan_directory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def write_annotation_files(report: dict[str, Any], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in report["items"]:
        target = output_dir / f"{Path(item['relative_path']).stem}.json"
        target.write_text(
            json.dumps(annotation_payload(item), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return len(report["items"])


def assign_dataset_splits(rows: list[Any]) -> dict[int, str]:
    """Assign whole projects/page-sequences to an approximately 80/20 split."""
    groups: dict[str, list[Any]] = {}
    for row in rows:
        # Missing grouping information stays in one quarantine-like group; it
        # is never scattered by row id, which would leak one sequence.
        key = (row.project_key or "").strip() or "unassigned"
        groups.setdefault(key, []).append(row)
    ordered = sorted(
        groups.items(),
        key=lambda item: hashlib.sha256(item[0].encode()).hexdigest(),
    )
    total = sum(len(items) for _, items in ordered)
    target = max(1, round(total * 0.2)) if total >= 5 and len(ordered) >= 2 else 0
    holdout_groups: set[str] = set()
    holdout_count = 0
    # Smallest groups first produces a closer target without splitting them.
    for key, items in sorted(ordered, key=lambda item: (len(item[1]), item[0])):
        if target and holdout_count < target and holdout_count + len(items) < total:
            holdout_groups.add(key)
            holdout_count += len(items)
    return {
        row.id: ("holdout" if key in holdout_groups else "calibration")
        for key, items in ordered
        for row in items
    }


def select_few_shot_annotations(
    rows: list[Any],
    *,
    orientation: str,
    page_role: str = "",
    limit: int = 5,
) -> list[Any]:
    """Retrieve only human-verified calibration company evidence."""
    eligible = [
        row for row in rows
        if row.status == "verified"
        and row.source_type == "company_published"
        and row.dataset_split == "calibration"
    ]
    eligible.sort(
        key=lambda row: (
            row.orientation != orientation,
            bool(page_role) and row.page_role != page_role,
            abs((row.canvas_width / max(1, row.canvas_height)) - (3 / 4)),
            row.id,
        )
    )
    return eligible[: max(0, min(5, limit))]


def _center(region: dict[str, Any]) -> tuple[float, float]:
    return region["x"] + region["width"] / 2, region["y"] + region["height"] / 2


def verified_statistics(rows: list[Any]) -> dict[str, Any]:
    verified = [
        row for row in rows
        if row.status == "verified" and row.source_type == "company_published"
    ]
    if not verified:
        return {
            "status": "not_ready",
            "verified_count": 0,
            "message": "No human-verified company_published annotations.",
        }
    per_image = [json.loads(row.regions_json or "[]") for row in verified]
    by_type: dict[str, list[dict[str, Any]]] = {
        kind: [region for regions in per_image for region in regions if region["type"] == kind]
        for kind in COLOR_TYPES.values()
    }
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None
    relationships = Counter()
    margin_samples: list[dict[str, float]] = []
    grid_columns: Counter[int] = Counter()
    for regions in per_image:
        if regions:
            margin_samples.append({
                "left": min(r["x"] for r in regions),
                "top": min(r["y"] for r in regions),
                "right": min(1 - r["x"] - r["width"] for r in regions),
                "bottom": min(1 - r["y"] - r["height"] for r in regions),
            })
            x_centers = sorted(_center(r)[0] for r in regions)
            clusters: list[float] = []
            for center in x_centers:
                if not clusters or abs(center - clusters[-1]) > 0.12:
                    clusters.append(center)
            grid_columns[len(clusters)] += 1
        products = [r for r in regions if r["type"] == "product_image"]
        texts = [r for r in regions if r["type"] == "main_text"]
        if products and texts:
            px, py = _center(max(products, key=lambda r: r["width"] * r["height"]))
            tx, ty = _center(max(texts, key=lambda r: r["width"] * r["height"]))
            relationships["text_above_product" if ty < py else "text_below_product"] += 1
            relationships["text_left_of_product" if tx < px else "text_right_of_product"] += 1
    return {
        "status": "ready",
        "verified_count": len(verified),
        "canvas_ratios": dict(Counter(canvas_ratio(r.canvas_width, r.canvas_height) for r in verified)),
        "orientations": dict(Counter(r.orientation for r in verified)),
        "average_modules_per_image": mean([len(regions) for regions in per_image]),
        "product_image": {
            "count": len(by_type["product_image"]),
            "mean_x": mean([r["x"] for r in by_type["product_image"]]),
            "mean_y": mean([r["y"] for r in by_type["product_image"]]),
            "mean_area": mean([r["width"] * r["height"] for r in by_type["product_image"]]),
        },
        "main_text": {
            "count": len(by_type["main_text"]),
            "mean_x": mean([r["x"] for r in by_type["main_text"]]),
            "mean_y": mean([r["y"] for r in by_type["main_text"]]),
            "mean_area": mean([r["width"] * r["height"] for r in by_type["main_text"]]),
        },
        "product_text_relationships": dict(relationships),
        "mean_outer_margins": {
            side: mean([sample[side] for sample in margin_samples])
            for side in ("top", "right", "bottom", "left")
        },
        "observed_column_clusters": dict(grid_columns),
        "reading_order_evidence": "Derived from top/bottom and left/right centers; text subtypes require model suggestion plus human review.",
        "page_roles": dict(Counter(r.page_role for r in verified)),
        "anomaly_ids": [
            r.id for r, regions in zip(verified, per_image)
            if not any(x["type"] == "product_image" for x in regions)
            or not any(x["type"] == "main_text" for x in regions)
        ],
    }


def evaluate_regions(predicted: list[dict[str, Any]], truth: list[dict[str, Any]]) -> dict[str, Any]:
    """Greedy one-to-one IoU evaluation, sufficient for deterministic holdout gates."""
    pairs: list[tuple[float, int, int]] = []
    out_of_bounds = 0
    text_types = {"main_title", "subtitle", "selling_point", "body_text", "main_text"}
    def family(value: str) -> str:
        return "main_text" if value in text_types else value
    for pi, pred in enumerate(predicted):
        if (
            min(pred.get("x", -1), pred.get("y", -1), pred.get("width", -1), pred.get("height", -1)) < 0
            or pred.get("x", 0) + pred.get("width", 0) > 1
            or pred.get("y", 0) + pred.get("height", 0) > 1
        ):
            out_of_bounds += 1
        for ti, target in enumerate(truth):
            if family(str(pred.get("type"))) == family(str(target.get("type"))):
                pairs.append((_iou(pred, target), pi, ti))
    matched_p: set[int] = set()
    matched_t: set[int] = set()
    matches: list[tuple[float, int, int]] = []
    for score, pi, ti in sorted(pairs, reverse=True):
        if score >= 0.1 and pi not in matched_p and ti not in matched_t:
            matched_p.add(pi); matched_t.add(ti); matches.append((score, pi, ti))
    def type_iou(kind: str) -> float | None:
        values = [
            score for score, pi, _ in matches
            if family(str(predicted[pi].get("type"))) == kind
        ]
        return round(sum(values) / len(values), 4) if values else None
    correct_type = sum(
        family(str(predicted[pi].get("type"))) == family(str(truth[ti].get("type")))
        for _, pi, ti in matches
    )
    def recall(kind: str) -> float:
        total = sum(family(str(item.get("type"))) == kind for item in truth)
        matched = sum(
            score >= 0.5 and family(str(truth[ti].get("type"))) == kind
            for score, _, ti in matches
        )
        return round(matched / total, 4) if total else 1.0
    return {
        "product_image_iou": type_iou("product_image"),
        "main_text_iou": type_iou("main_text"),
        "layout_block_mean_iou": type_iou("layout_block"),
        "product_image_accuracy": recall("product_image"),
        "main_text_accuracy": recall("main_text"),
        "module_type_accuracy": round(correct_type / len(matches), 4) if matches else 0.0,
        "missed": len(truth) - len(matched_t),
        "extra": len(predicted) - len(matched_p),
        "out_of_bounds": out_of_bounds,
        "coordinate_validity": round((len(predicted) - out_of_bounds) / len(predicted), 4) if predicted else 1.0,
    }
