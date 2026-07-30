"""Validated, transactional import/export for layout-search acceptance packs."""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from . import layout_search, models

RESULT_TYPES = {"case", "pattern"}
RELEVANCE_VALUES = {"relevant", "partially_relevant", "irrelevant"}
DATASET_SPLITS = {"calibration", "holdout"}


def parse_utc_datetime(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是 ISO 8601 时间字符串")
    text = value.strip()
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} 不是合法 ISO 8601 时间：{value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} 必须包含时区，例如 Z 或 +08:00")
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)


def utc_text(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def export_pack(db: Session, dataset_version: str) -> dict[str, Any]:
    dataset = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == dataset_version
    ).first()
    if not dataset:
        raise ValueError("数据集版本不存在")
    truth = layout_search.list_ground_truth(db, dataset_version)
    for row in truth:
        row["created_at"] = utc_text(row["created_at"])
        row["frozen_at"] = utc_text(row["frozen_at"])
    metadata = layout_search._dataset_dict(db, dataset)
    for key in ("created_at", "frozen_at", "last_run_at"):
        metadata[key] = utc_text(metadata[key])
    return {
        "format": "layout-search-acceptance-v1",
        "dataset_version": dataset_version,
        "dataset": metadata,
        "ground_truth": truth,
        "evaluation": layout_search.evaluation(db, dataset_version),
    }


def validate_pack(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("format") != "layout-search-acceptance-v1":
        raise ValueError("不支持的验收包格式")
    version = str(payload.get("dataset_version", "")).strip()
    metadata = payload.get("dataset")
    rows = payload.get("ground_truth")
    if not version or not isinstance(metadata, dict) or not isinstance(rows, list) or not rows:
        raise ValueError("缺少 dataset_version、dataset 元数据或 ground_truth")
    if metadata.get("dataset_version") != version:
        raise ValueError("数据集元数据版本不一致")
    created_at = parse_utc_datetime(metadata.get("created_at"), "dataset.created_at")
    frozen_at = parse_utc_datetime(metadata.get("frozen_at"), "dataset.frozen_at")
    last_run_at = (
        parse_utc_datetime(metadata["last_run_at"], "dataset.last_run_at")
        if metadata.get("last_run_at") else None
    )
    normalized = []
    requirement_splits: dict[int, set[str]] = {}
    requirement_types: dict[int, set[str]] = {}
    if metadata.get("dataset_kind") not in {"real", "fixture"}:
        raise ValueError("dataset.dataset_kind 非法")
    if frozen_at < created_at:
        raise ValueError("dataset.frozen_at 不能早于 created_at")
    for index, source in enumerate(rows):
        prefix = f"ground_truth[{index}]"
        if source.get("dataset_version") != version:
            raise ValueError(f"{prefix}.dataset_version 不一致")
        if source.get("result_type") not in RESULT_TYPES:
            raise ValueError(f"{prefix}.result_type 非法")
        if source.get("expected_relevance") not in RELEVANCE_VALUES:
            raise ValueError(f"{prefix}.expected_relevance 非法")
        if source.get("dataset_split") not in DATASET_SPLITS:
            raise ValueError(f"{prefix}.dataset_split 非法")
        if not str(source.get("reviewer", "")).strip():
            raise ValueError(f"{prefix}.reviewer 不能为空")
        if not str(source.get("reason", "")).strip():
            raise ValueError(f"{prefix}.reason 不能为空")
        row_created = parse_utc_datetime(source.get("created_at"), f"{prefix}.created_at")
        row_frozen = parse_utc_datetime(source.get("frozen_at"), f"{prefix}.frozen_at")
        requirement_id = int(source.get("requirement_id", 0))
        result_id = int(source.get("result_id", 0))
        requirement = db.get(models.BusinessRequirement, requirement_id)
        if not requirement:
            raise ValueError(f"{prefix} 需求 ID 不存在：{requirement_id}")
        if requirement.status != "confirmed":
            raise ValueError(f"{prefix} 需求不是 confirmed：{requirement_id}")
        target = models.LayoutPattern if source["result_type"] == "pattern" else models.Case
        if not db.get(target, result_id):
            raise ValueError(f"{prefix} 结果 ID 不存在：{result_id}")
        requirement_splits.setdefault(requirement_id, set()).add(source["dataset_split"])
        requirement_types.setdefault(requirement_id, set()).add(source["result_type"])
        if row_frozen < row_created:
            raise ValueError(f"{prefix}.frozen_at 不能早于 created_at")
        normalized.append({
            "requirement_id": requirement_id,
            "result_type": source["result_type"],
            "result_id": result_id,
            "expected_relevance": source["expected_relevance"],
            "reviewer": source["reviewer"].strip(),
            "reason": source["reason"].strip(),
            "dataset_version": version,
            "dataset_split": source["dataset_split"],
            "created_at": row_created,
            "frozen_at": row_frozen,
        })
    if any(len(splits) != 1 for splits in requirement_splits.values()):
        raise ValueError("同一需求不能跨 calibration/holdout split")
    missing_types = [
        requirement_id for requirement_id, types in requirement_types.items()
        if types != {"case", "pattern"}
    ]
    if missing_types:
        raise ValueError(f"需求必须同时包含案例和模式标注：{missing_types}")
    return {
        "version": version,
        "dataset": {
            "dataset_version": version,
            "name": str(metadata.get("name") or version),
            "description": str(metadata.get("description") or ""),
            "dataset_kind": metadata.get("dataset_kind", "real"),
            "created_by": str(metadata.get("created_by") or "import"),
            "created_at": created_at, "frozen_at": frozen_at,
            "last_run_at": last_run_at,
        },
        "rows": normalized,
    }


def import_pack(db: Session, payload: dict[str, Any], *, execute: bool = False):
    try:
        validated = validate_pack(db, payload)
        exists = db.query(models.LayoutSearchDataset).filter(
            models.LayoutSearchDataset.dataset_version == validated["version"]
        ).first() or db.query(models.LayoutSearchGroundTruth).filter(
            models.LayoutSearchGroundTruth.dataset_version == validated["version"]
        ).first()
        if exists:
            raise ValueError("目标版本已存在，禁止覆盖")
        result = {
            "dry_run": not execute, "dataset_version": validated["version"],
            "annotation_count": len(validated["rows"]), "valid": True,
        }
        if not execute:
            db.rollback()
            return result
        db.add(models.LayoutSearchDataset(**validated["dataset"]))
        db.add_all(models.LayoutSearchGroundTruth(**row) for row in validated["rows"])
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
