"""Pair colored-box annotations with unannotated originals, conservatively."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_item(
    row: models.DisinfectionAnnotation,
    *,
    original_path: str = "",
    pair_status: str,
    warning_count: int,
    recommended_next_action: str,
    candidate: dict | None = None,
) -> dict:
    item = {
        "filename": Path(row.annotated_image_path).name,
        "annotation_id": row.id,
        "case_id": None,
        "annotated_path": row.annotated_image_path,
        "original_path": original_path,
        "original_pair_status": pair_status,
        "project_key": row.project_key or "",
        "page_role": row.page_role or "other",
        "warning_count": warning_count,
        "review_status": row.status,
        "reviewer": row.reviewer or "",
        "recommended_next_action": recommended_next_action,
    }
    if candidate:
        item.update({
            "candidate_original_path": candidate["original_path"],
            "mean_difference": candidate["mean_difference"],
            "second_candidate_path": candidate["second_path"],
            "second_difference": candidate["second_difference"],
            "margin": candidate["margin"],
            "candidate_confidence": candidate["pairing_status"],
        })
    return item


def _meaningful_warnings(raw: str) -> list[str]:
    return [
        warning for warning in json.loads(raw or "[]")
        if warning != "unannotated_original_not_found"
    ]


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
                models.DisinfectionAnnotation.source_type == "company_published",
                models.DisinfectionAnnotation.product_category == args.product_category,
            )
            .order_by(models.DisinfectionAnnotation.id)
            .all()
        )
        exact_pairs: list[dict] = []
        unpaired: list[models.DisinfectionAnnotation] = []
        for row in annotations:
            warnings = _meaningful_warnings(row.warnings_json)
            stored_original = Path(row.original_image_path).resolve() if row.original_image_path else None
            if stored_original and stored_original.is_file():
                next_action = (
                    "补充project_key后人工确认" if not (row.project_key or "").strip()
                    else "补充page_role后人工确认" if (row.page_role or "other") == "other"
                    else "已确认" if row.status == "verified"
                    else "人工检查标注并确认verified"
                )
                exact_pairs.append(_review_item(
                    row,
                    original_path=str(stored_original),
                    pair_status="exact",
                    warning_count=len(warnings),
                    recommended_next_action=next_action,
                ))
            else:
                unpaired.append(row)

        candidates = pair(unpaired, originals) if unpaired else []
        needs_human_pairing = []
        for row, candidate in zip(unpaired, candidates):
            warnings = _meaningful_warnings(row.warnings_json)
            needs_human_pairing.append(_review_item(
                row,
                pair_status="needs_human_pairing",
                warning_count=len(warnings),
                recommended_next_action="人工对照候选原图，确认后再保存配对",
                candidate=candidate,
            ))

        sha_groups: dict[str, list[str]] = defaultdict(list)
        stem_groups: dict[str, list[str]] = defaultdict(list)
        for path in originals:
            sha_groups[_sha256(path)].append(str(path.resolve()))
            stem_groups[path.stem.casefold()].append(str(path.resolve()))
        duplicate_files = [paths for paths in sha_groups.values() if len(paths) > 1]
        filename_conflicts = [paths for paths in stem_groups.values() if len(paths) > 1]

        size_mismatches = []
        for item in exact_pairs + needs_human_pairing:
            original = item.get("original_path") or item.get("candidate_original_path")
            row = next(row for row in annotations if row.id == item["annotation_id"])
            with Image.open(original) as original_image:
                original_size = original_image.size
            annotated_size = (row.canvas_width, row.canvas_height)
            if original_size != annotated_size:
                size_mismatches.append({
                    "annotation_id": row.id,
                    "annotated_size": list(annotated_size),
                    "original_size": list(original_size),
                    "original_path": original,
                })

        report = {
            "product_category": args.product_category,
            "annotation_count": len(annotations),
            "verified_annotations": sum(row.status == "verified" for row in annotations),
            "pending_review_annotations": sum(row.status == "pending_review" for row in annotations),
            "original_candidates": len(originals),
            "exact_pair_count": len(exact_pairs),
            "needs_human_pairing_count": len(needs_human_pairing),
            "missing_original_count": 0 if originals else len(unpaired),
            "duplicate_file_group_count": len(duplicate_files),
            "filename_conflict_group_count": len(filename_conflicts),
            "size_mismatch_count": len(size_mismatches),
            "project_key_missing_count": sum(not (row.project_key or "").strip() for row in annotations),
            "page_role_missing_count": sum((row.page_role or "other") == "other" for row in annotations),
            "source_type_error_count": sum(row.source_type != "company_published" for row in annotations),
            "ambiguous_annotation_count": sum(bool(_meaningful_warnings(row.warnings_json)) for row in annotations),
            "exact_pairs": exact_pairs,
            "needs_human_pairing": needs_human_pairing,
            "missing_originals": [] if originals else [
                _review_item(
                    row,
                    pair_status="missing_original",
                    warning_count=len(_meaningful_warnings(row.warnings_json)),
                    recommended_next_action="补充无彩框公司成品原图",
                ) for row in unpaired
            ],
            "duplicate_files": duplicate_files,
            "filename_conflicts": filename_conflicts,
            "size_mismatches": size_mismatches,
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if args.contact_sheets:
            write_contact_sheets(candidates, Path(args.contact_sheets))
        print(json.dumps({
            key: report[key] for key in (
                "product_category", "annotation_count", "verified_annotations",
                "pending_review_annotations", "original_candidates",
                "exact_pair_count", "needs_human_pairing_count",
                "missing_original_count", "duplicate_file_group_count",
                "filename_conflict_group_count", "size_mismatch_count",
                "project_key_missing_count", "page_role_missing_count",
                "source_type_error_count", "ambiguous_annotation_count",
            )
        }, ensure_ascii=False, indent=2))
        if not args.execute:
            print("DRY RUN: database unchanged")
            return 0
        raise SystemExit(
            "automatic similarity pairing is disabled; confirm candidates through human review"
        )
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
