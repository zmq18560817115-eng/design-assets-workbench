"""Dry-run or idempotently import colored-box annotations for human review."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.disinfection_annotations import scan_directory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ROOT / "Untitled"))
    parser.add_argument(
        "--report",
        default=str(ROOT / "backend/evaluation/disinfection_cabinet_layout_report.json"),
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"source directory not found: {source}")
    report = scan_directory(source)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: report[key] for key in ("total", "formats", "sizes", "orientations", "region_totals", "pairing")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        print("DRY RUN: database unchanged; model not called; files not copied")
        return 0
    init_db()
    db = SessionLocal()
    try:
        batch_id = uuid.uuid5(uuid.NAMESPACE_URL, f"disinfection:{source}").hex
        batch = db.get(models.DisinfectionAnnotationBatch, batch_id)
        if not batch:
            batch = models.DisinfectionAnnotationBatch(id=batch_id)
            db.add(batch)
        batch.source_root = str(source)
        batch.total = report["total"]
        batch.status = "pending_review"
        batch.scan_report_json = json.dumps(summary, ensure_ascii=False)
        for item in report["items"]:
            record = (
                db.query(models.DisinfectionAnnotation)
                .filter(models.DisinfectionAnnotation.source_sha256 == item["sha256"])
                .first()
            )
            if record:
                continue
            record = models.DisinfectionAnnotation(
                batch_id=batch_id,
                annotated_image_path=str(source / item["relative_path"]),
                source_sha256=item["sha256"],
                canvas_width=item["width"],
                canvas_height=item["height"],
                orientation=item["orientation"],
                regions_json=json.dumps(item["regions"], ensure_ascii=False),
                warnings_json=json.dumps(item["warnings"], ensure_ascii=False),
            )
            db.add(record)
            db.flush()
            db.add(models.DisinfectionAnnotationVersion(
                annotation_id=record.id,
                version=1,
                payload_json=json.dumps(item, ensure_ascii=False),
                source="color_box_parser_v1",
            ))
        db.commit()
    finally:
        db.close()
    print("EXECUTE: annotations stored as pending_review; no row was auto-verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
