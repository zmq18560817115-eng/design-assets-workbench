"""Shared manifest preparation and persisted batch execution."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import batch
from .business_contract import ManifestReport, inferred_metadata, parse_manifest


def prepare_manifest(
    root: Path,
    manifest: Path | None,
    *,
    default_source_type: str,
    inferred_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], ManifestReport | None]:
    if manifest:
        report = parse_manifest(root, manifest, default_source_type)
        items = report.rows
    else:
        report = None
        items = []
        for raw in inferred_items:
            item = inferred_metadata(**raw)
            item.update(raw)
            item["source_type"] = default_source_type
            item["metadata_status"] = "inferred"
            items.append(item)
    for item in items:
        path = Path(item["path"])
        item.setdefault("filename", path.name)
        item.setdefault("asset_category", item.pop("category", "layout"))
        item.setdefault("asset_subcategory", item.pop("subcategory", ""))
        item.setdefault("source_url", str(path))
        item.setdefault("uploader", "manifest-import")
        item["copy_to_uploads"] = True
    return items, report


def dry_run_summary(items: list[dict], report: ManifestReport | None) -> dict[str, Any]:
    return {
        "total": len(items),
        "source_types": dict(Counter(item.get("source_type", "") for item in items)),
        "business_lines": dict(Counter(item.get("business_line", "") for item in items)),
        "product_categories": dict(
            Counter(item.get("product_category", "") for item in items)
        ),
        "metadata_status": dict(
            Counter(item.get("metadata_status", "") for item in items)
        ),
        "missing_fields": report.missing_fields if report else [],
        "invalid_rows": report.invalid_rows if report else [],
        "missing_files": report.missing_files if report else [],
        "duplicates": report.duplicates if report else [],
        "valid": report.valid if report else True,
    }


def execute_items(
    items: list[dict],
    *,
    concurrency: int | None = None,
    enable_vlm: bool = True,
) -> dict[str, Any]:
    batch_id = batch.create_batch(
        items,
        background=False,
        concurrency=concurrency,
        enable_vlm=enable_vlm,
    )
    return {"batch_id": batch_id, **(batch.get_batch(batch_id) or {})}
