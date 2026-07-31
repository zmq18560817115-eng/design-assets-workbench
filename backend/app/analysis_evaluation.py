"""Governed calibration and sealed holdout lifecycle for visual decomposition."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from . import models


DATASET_STATES = (
    "draft",
    "gt_ready",
    "calibration_active",
    "calibration_passed",
    "version_frozen",
    "holdout_ready",
    "holdout_running",
    "passed",
    "failed",
    "consumed",
)


class EvaluationConflict(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def content_hash(value: Any) -> str:
    text = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dataset_or_error(db: Session, version: str) -> models.AnalysisEvaluationDataset:
    row = (
        db.query(models.AnalysisEvaluationDataset)
        .filter(models.AnalysisEvaluationDataset.dataset_version == version)
        .first()
    )
    if not row:
        raise LookupError("AI拆解数据集不存在")
    return row


def create_dataset(db: Session, payload: dict) -> models.AnalysisEvaluationDataset:
    if (
        db.query(models.AnalysisEvaluationDataset)
        .filter(
            models.AnalysisEvaluationDataset.dataset_version
            == payload["dataset_version"]
        )
        .first()
    ):
        raise EvaluationConflict("dataset_version 已存在")
    row = models.AnalysisEvaluationDataset(**payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def assign_item(
    db: Session, dataset: models.AnalysisEvaluationDataset, payload: dict
) -> models.AnalysisEvaluationItem:
    if dataset.status not in {"draft", "gt_ready"}:
        raise EvaluationConflict("数据集进入校准后不可修改 split")
    if not db.get(models.Case, payload["case_id"]):
        raise LookupError("案例不存在")
    existing = (
        db.query(models.AnalysisEvaluationItem)
        .filter(
            models.AnalysisEvaluationItem.dataset_id == dataset.id,
            models.AnalysisEvaluationItem.case_id == payload["case_id"],
        )
        .first()
    )
    if existing and existing.dataset_split != payload["dataset_split"]:
        raise EvaluationConflict("同一案例不能同时属于 calibration 和 holdout")
    if existing:
        existing.reviewer = payload.get("reviewer", existing.reviewer)
        existing.reason = payload.get("reason", existing.reason)
        row = existing
    else:
        row = models.AnalysisEvaluationItem(dataset_id=dataset.id, **payload)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_ground_truth(
    db: Session,
    dataset: models.AnalysisEvaluationDataset,
    item: models.AnalysisEvaluationItem,
    payload: dict,
) -> models.AnalysisEvaluationItem:
    if dataset.status not in {"draft", "gt_ready"}:
        raise EvaluationConflict("Ground Truth 已锁定")
    item.ground_truth_json = _json(
        {key: value for key, value in payload.items() if key not in {"reviewer", "reason"}}
    )
    item.gt_status = "ready"
    item.reviewer = payload["reviewer"]
    item.reason = payload["reason"]
    ready = all(
        row.gt_status == "ready"
        for row in db.query(models.AnalysisEvaluationItem)
        .filter(models.AnalysisEvaluationItem.dataset_id == dataset.id)
        .all()
    )
    if ready:
        dataset.status = "gt_ready"
    db.commit()
    db.refresh(item)
    return item


def serialize_item(
    item: models.AnalysisEvaluationItem, *, include_ground_truth: bool
) -> dict:
    result = {
        "id": item.id,
        "case_id": item.case_id,
        "dataset_split": item.dataset_split,
        "gt_status": item.gt_status,
        "reviewer": item.reviewer,
        "reason": item.reason,
    }
    if include_ground_truth:
        result["ground_truth"] = _load(item.ground_truth_json, {})
    return result


def dataset_detail(
    db: Session,
    dataset: models.AnalysisEvaluationDataset,
    *,
    admin: bool,
) -> dict:
    items = (
        db.query(models.AnalysisEvaluationItem)
        .filter(models.AnalysisEvaluationItem.dataset_id == dataset.id)
        .order_by(models.AnalysisEvaluationItem.id)
        .all()
    )
    counts = {
        split: sum(item.dataset_split == split for item in items)
        for split in ("calibration", "holdout")
    }
    visible = []
    for item in items:
        if item.dataset_split == "holdout" and not admin:
            continue
        visible.append(
            serialize_item(
                item,
                include_ground_truth=admin and item.dataset_split == "calibration",
            )
        )
    return {
        "id": dataset.id,
        "dataset_version": dataset.dataset_version,
        "name": dataset.name,
        "product_category": dataset.product_category,
        "description": dataset.description,
        "status": dataset.status,
        "sealed": bool(dataset.sealed_at),
        "consumed": dataset.status == "consumed",
        "counts": counts,
        "items": visible,
        "created_by": dataset.created_by,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def runtime_to_dict(row: models.AnalysisRuntimeVersion, *, technical: bool) -> dict:
    result = {
        "id": row.id,
        "model_name": row.model_name,
        "model_provider": row.model_provider,
        "prompt_version": row.prompt_version,
        "prompt_hash": row.prompt_hash,
        "validator_version": row.validator_version,
        "validator_hash": row.validator_hash,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "frozen_at": row.frozen_at,
    }
    if technical:
        result["prompt_text"] = row.prompt_text
        result["validator_config"] = _load(row.validator_config_json, {})
    return result


def create_runtime(db: Session, payload: dict) -> models.AnalysisRuntimeVersion:
    validator_config = payload.pop("validator_config")
    row = models.AnalysisRuntimeVersion(
        **payload,
        prompt_hash=content_hash(payload.get("prompt_text", "")),
        validator_config_json=_json(validator_config),
        validator_hash=content_hash(validator_config),
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise EvaluationConflict("该模型、Prompt、Validator版本组合已存在")
    db.refresh(row)
    return row


def mark_consumed(
    dataset: models.AnalysisEvaluationDataset,
    *,
    now: dt.datetime | None = None,
) -> None:
    dataset.status = "consumed"
    dataset.consumed_at = now or dt.datetime.utcnow()
