"""Canonical business metadata contract for company and reference assets."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PAGE_ROLES = (
    "cover_hook",
    "problem_statement",
    "cause_explanation",
    "product_display",
    "function_explanation",
    "parameter_comparison",
    "usage_step",
    "service_assurance",
    "conclusion",
    "call_to_action",
    "other",
)

NEW_SOURCE_TYPES = (
    "company_published",
    "external_reference",
    "rejected_company_design",
    "company_revision",
)
HISTORICAL_SOURCE_TYPES = ("company_finished_asset", "internal_reference")
SUPPORTED_SOURCE_TYPES = NEW_SOURCE_TYPES + HISTORICAL_SOURCE_TYPES

MANIFEST_FIELDS = (
    "relative_path",
    "source_type",
    "business_line",
    "product_category",
    "product_name",
    "channel",
    "content_purpose",
    "campaign_stage",
    "page_role",
    "sequence_index",
    "project_name",
    "brief_ref",
    "review_decision",
    "reviewer",
    "notes",
)


@dataclass
class ManifestReport:
    rows: list[dict[str, Any]] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    invalid_rows: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not (self.missing_fields or self.invalid_rows or self.missing_files)


def normalize_source_type(value: str, default: str) -> str:
    value = (value or default).strip()
    if value not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"invalid source_type: {value}")
    return value


def normalize_page_role(value: str) -> str:
    value = (value or "other").strip()
    if value not in PAGE_ROLES:
        raise ValueError(f"invalid page_role: {value}")
    return value


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("items", [])
        if not isinstance(payload, list):
            raise ValueError("JSON manifest must be a list or contain an items list")
        return [dict(row) for row in payload]
    raise ValueError("manifest must be CSV or JSON")


def parse_manifest(root: Path, path: Path, default_source_type: str) -> ManifestReport:
    report = ManifestReport()
    raw_rows = _load_rows(path)
    available = set(raw_rows[0]) if raw_rows else set()
    report.missing_fields = [name for name in MANIFEST_FIELDS if name not in available]
    seen: set[str] = set()
    for index, raw in enumerate(raw_rows, 2):
        relative = str(raw.get("relative_path") or "").strip().replace("\\", "/")
        if not relative:
            report.invalid_rows.append(f"row {index}: relative_path is required")
            continue
        if relative in seen:
            report.duplicates.append(relative)
            continue
        seen.add(relative)
        full_path = (root / relative).resolve()
        try:
            full_path.relative_to(root.resolve())
        except ValueError:
            report.invalid_rows.append(f"row {index}: path escapes root")
            continue
        if not full_path.is_file():
            report.missing_files.append(relative)
        try:
            source_type = normalize_source_type(
                str(raw.get("source_type") or ""), default_source_type
            )
            page_role = normalize_page_role(str(raw.get("page_role") or ""))
            raw_index = str(raw.get("sequence_index") or "").strip()
            sequence_index = int(raw_index) if raw_index else None
            if sequence_index is not None and sequence_index < 0:
                raise ValueError("sequence_index must be >= 0")
        except ValueError as exc:
            report.invalid_rows.append(f"row {index}: {exc}")
            continue
        item = {name: str(raw.get(name) or "").strip() for name in MANIFEST_FIELDS}
        item.update(
            {
                "path": full_path,
                "relative_path": relative,
                "source_type": source_type,
                "page_role": page_role,
                "sequence_index": sequence_index,
                "metadata_status": "manifest",
            }
        )
        report.rows.append(item)
    return report


def inferred_metadata(**values: Any) -> dict[str, Any]:
    result = {name: "" for name in MANIFEST_FIELDS}
    result.update(values)
    result.setdefault("page_role", "other")
    result["metadata_status"] = "inferred"
    return result
