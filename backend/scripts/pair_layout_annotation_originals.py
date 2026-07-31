"""Pair colored-box annotations with unannotated originals, conservatively."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
RESIZED = (192, 256)


def _image(path: Path, cache: dict[Path, Image.Image]) -> Image.Image:
    if path not in cache:
        cache[path] = Image.open(path).convert("RGB").resize(RESIZED)
    return cache[path]


def _annotation_mask(image: Image.Image) -> Image.Image:
    mask = Image.new("L", image.size)
    mask.putdata([
        255 if (
            (red > 210 and green < 90 and blue < 90)
            or (blue > 180 and red < 100 and green < 210)
            or (green > 100 and red < 120 and blue < 130)
        ) else 0
        for red, green, blue in image.getdata()
    ])
    return mask


def _mean_difference(
    annotated: Image.Image,
    original: Image.Image,
    annotation_mask: Image.Image,
) -> float:
    # Substitute candidate pixels under colored strokes, then compare the
    # remaining artwork. This prevents the human boxes from dominating score.
    corrected = Image.composite(original, annotated, annotation_mask)
    histogram = ImageChops.difference(corrected, original).histogram()
    total = sum(count * (index % 256) for index, count in enumerate(histogram))
    return total / (RESIZED[0] * RESIZED[1] * 3)


def pair(
    annotations: list[models.DisinfectionAnnotation],
    originals: list[Path],
) -> list[dict]:
    cache: dict[Path, Image.Image] = {}
    results: list[dict] = []
    for row in annotations:
        annotated_path = Path(row.annotated_image_path).resolve()
        annotated = _image(annotated_path, cache)
        mask = _annotation_mask(annotated)
        ranked = sorted(
            (
                _mean_difference(annotated, _image(path, cache), mask),
                path.resolve(),
            )
            for path in originals
        )
        best, second = ranked[:2]
        margin = second[0] - best[0]
        results.append({
            "annotation_id": row.id,
            "annotated_path": str(annotated_path),
            "original_path": str(best[1]),
            "mean_difference": round(best[0], 3),
            "second_path": str(second[1]),
            "second_difference": round(second[0], 3),
            "margin": round(margin, 3),
            "pairing_status": (
                "high_confidence" if best[0] <= 20 and margin >= 15
                else "manual_review"
            ),
        })
    return results


def write_contact_sheets(results: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for page in range((len(results) + 9) // 10):
        batch = results[page * 10:(page + 1) * 10]
        sheet = Image.new("RGB", (1500, 620), "white")
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(batch):
            column, row = index % 5, index // 5
            left, top = column * 300, row * 310
            annotated = Image.open(item["annotated_path"]).convert("RGB")
            original = Image.open(item["original_path"]).convert("RGB")
            annotated.thumbnail((135, 250))
            original.thumbnail((135, 250))
            sheet.paste(annotated, (left + 5, top + 42))
            sheet.paste(original, (left + 155, top + 42))
            draw.text(
                (left + 5, top + 5),
                f"ID {item['annotation_id']} diff {item['mean_difference']} "
                f"gap {item['margin']}",
                fill="black",
            )
            draw.text(
                (left + 5, top + 22),
                Path(item["original_path"]).name,
                fill="black",
            )
        sheet.save(output_dir / f"pairing-{page + 1}.jpg", quality=90)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--originals", required=True)
    parser.add_argument("--product-category", default="消毒柜")
    parser.add_argument("--report", required=True)
    parser.add_argument("--contact-sheets")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    originals_root = Path(args.originals).resolve()
    originals = sorted(
        path for path in originals_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if len(originals) < 2:
        raise SystemExit("at least two original images are required")

    db = SessionLocal()
    try:
        annotations = (
            db.query(models.DisinfectionAnnotation)
            .filter(
                models.DisinfectionAnnotation.status == "verified",
                models.DisinfectionAnnotation.source_type == "company_published",
                models.DisinfectionAnnotation.product_category == args.product_category,
            )
            .order_by(models.DisinfectionAnnotation.id)
            .all()
        )
        results = pair(annotations, originals)
        report = {
            "product_category": args.product_category,
            "verified_annotations": len(annotations),
            "original_candidates": len(originals),
            "high_confidence": sum(
                item["pairing_status"] == "high_confidence" for item in results
            ),
            "manual_review": sum(
                item["pairing_status"] == "manual_review" for item in results
            ),
            "items": results,
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if args.contact_sheets:
            write_contact_sheets(results, Path(args.contact_sheets))
        print(json.dumps({
            key: report[key] for key in (
                "product_category", "verified_annotations",
                "original_candidates", "high_confidence", "manual_review",
            )
        }, ensure_ascii=False, indent=2))
        if not args.execute:
            print("DRY RUN: database unchanged")
            return 0
        for row, item in zip(annotations, results):
            if item["pairing_status"] == "high_confidence":
                row.original_image_path = item["original_path"]
        db.commit()
        print("EXECUTE: high-confidence original paths stored")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
