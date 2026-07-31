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
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=lambda item: item.isoformat() if isinstance(item, (dt.date, dt.datetime)) else str(item),
    )


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
        if (
            item.dataset_split == "holdout"
            and dataset.sealed_at
            and dataset.status != "consumed"
        ):
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


def _latest_blueprint(db: Session, case_id: int) -> models.LayoutBlueprint | None:
    return (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.case_id == case_id)
        .order_by(models.LayoutBlueprint.version.desc())
        .first()
    )


def _region_valid(region: dict) -> bool:
    try:
        x, y = float(region["x"]), float(region["y"])
        width, height = float(region["width"]), float(region["height"])
        return (
            0 <= x <= 1 and 0 <= y <= 1 and width > 0 and height > 0
            and x + width <= 1.000001 and y + height <= 1.000001
        )
    except (KeyError, TypeError, ValueError):
        return False


def _overlap_ratio(left: dict, right: dict) -> float:
    x1, y1 = max(left["x"], right["x"]), max(left["y"], right["y"])
    x2 = min(left["x"] + left["width"], right["x"] + right["width"])
    y2 = min(left["y"] + left["height"], right["y"] + right["height"])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    smaller = min(left["width"] * left["height"], right["width"] * right["height"])
    return intersection / smaller if smaller else 0.0


def evaluate_item(
    db: Session,
    item: models.AnalysisEvaluationItem,
    validator_config: dict,
) -> dict:
    blueprint = _latest_blueprint(db, item.case_id)
    if not blueprint:
        return {
            "status": "failed", "error_code": "PRODUCT_MISSED",
            "metrics": {"schema_valid": 0, "product_detected": 0, "module_detected": 0},
            "prediction": {},
        }
    modules = _load(blueprint.modules_json, [])
    if not isinstance(modules, list) or any(not _region_valid(row) for row in modules):
        return {
            "status": "failed", "error_code": "OUTPUT_SCHEMA_INVALID",
            "metrics": {"schema_valid": 0, "product_detected": 0, "module_detected": 0},
            "prediction": {"blueprint_id": blueprint.id},
        }
    product = [row for row in modules if row.get("type") == "product_image"]
    if not product:
        return {
            "status": "failed", "error_code": "PRODUCT_MISSED",
            "metrics": {"schema_valid": 1, "product_detected": 0, "module_detected": int(bool(modules))},
            "prediction": {"blueprint_id": blueprint.id, "module_count": len(modules)},
        }
    threshold = float(validator_config.get("maximum_overlap_ratio", 0.85))
    allowed = {tuple(sorted(pair)) for pair in _load(item.ground_truth_json, {}).get("allowed_overlaps", [])}
    for index, left in enumerate(modules):
        for right in modules[index + 1:]:
            pair = tuple(sorted((str(left.get("id", "")), str(right.get("id", "")))))
            if pair not in allowed and _overlap_ratio(left, right) > threshold:
                return {
                    "status": "failed", "error_code": "MODULE_OVERLAP",
                    "metrics": {"schema_valid": 1, "product_detected": 1, "module_detected": 1},
                    "prediction": {"blueprint_id": blueprint.id, "overlap_pair": pair},
                }
    return {
        "status": "passed", "error_code": "",
        "metrics": {"schema_valid": 1, "product_detected": 1, "module_detected": int(bool(modules))},
        "prediction": {"blueprint_id": blueprint.id, "module_count": len(modules)},
    }


def freeze_runtime(
    db: Session,
    dataset: models.AnalysisEvaluationDataset,
    runtime: models.AnalysisRuntimeVersion,
) -> None:
    if dataset.status != "calibration_passed" or runtime.status != "calibration_passed":
        raise EvaluationConflict("calibration 未通过，不能冻结版本")
    now = dt.datetime.utcnow()
    runtime.status = "frozen"
    runtime.frozen_at = now
    dataset.status = "holdout_ready"
    dataset.sealed_at = now
    db.commit()


def run_evaluation(
    db: Session,
    dataset: models.AnalysisEvaluationDataset,
    runtime: models.AnalysisRuntimeVersion,
    *,
    dataset_split: str,
    actor: str,
    confirm_holdout: bool,
) -> models.AnalysisEvaluationRun:
    if dataset.status == "consumed":
        raise EvaluationConflict("consumed 数据集不能再次运行")
    if dataset_split == "calibration":
        if dataset.status not in {"gt_ready", "calibration_active", "calibration_passed"}:
            raise EvaluationConflict("Ground Truth 未就绪，不能运行 calibration")
        if runtime.status not in {"draft", "calibration_passed"}:
            raise EvaluationConflict("该版本状态不能运行 calibration")
        formal = False
        dataset.status = "calibration_active"
    else:
        if not confirm_holdout:
            raise EvaluationConflict("必须确认本次运行会消耗当前 Holdout")
        if dataset.status != "holdout_ready" or runtime.status != "frozen":
            raise EvaluationConflict("未冻结版本或 calibration 未通过，不能运行 holdout")
        formal = True
        dataset.status = "holdout_running"
    existing = (
        db.query(models.AnalysisEvaluationRun)
        .filter(
            models.AnalysisEvaluationRun.dataset_id == dataset.id,
            models.AnalysisEvaluationRun.dataset_split == dataset_split,
            models.AnalysisEvaluationRun.runtime_version_id == runtime.id,
            models.AnalysisEvaluationRun.formal == formal,
        )
        .first()
    )
    if existing:
        raise EvaluationConflict("同一数据集和版本组合只能执行一次")
    now = dt.datetime.utcnow()
    snapshot = runtime_to_dict(runtime, technical=False)
    run = models.AnalysisEvaluationRun(
        dataset_id=dataset.id,
        dataset_split=dataset_split,
        runtime_version_id=runtime.id,
        formal=formal,
        run_status="running",
        version_snapshot_json=_json(snapshot),
        started_at=now,
        created_by=actor,
    )
    db.add(run)
    db.flush()
    items = (
        db.query(models.AnalysisEvaluationItem)
        .filter(
            models.AnalysisEvaluationItem.dataset_id == dataset.id,
            models.AnalysisEvaluationItem.dataset_split == dataset_split,
            models.AnalysisEvaluationItem.gt_status == "ready",
        )
        .all()
    )
    if not items:
        db.rollback()
        raise EvaluationConflict(f"{dataset_split} 没有完整 Ground Truth")
    validator = _load(runtime.validator_config_json, {})
    outcomes = []
    for item in items:
        outcome = evaluate_item(db, item, validator)
        outcomes.append(outcome)
        db.add(models.AnalysisEvaluationResult(
            run_id=run.id, item_id=item.id, status=outcome["status"],
            error_code=outcome["error_code"], metrics_json=_json(outcome["metrics"]),
            prediction_json=_json(outcome["prediction"]),
        ))
    total = len(outcomes)
    passed = sum(row["status"] == "passed" for row in outcomes)
    aggregate = {
        "total": total,
        "passed_items": passed,
        "pass_rate": round(passed / total, 4),
        "timeout_rate": round(sum(row["error_code"] == "MODEL_TIMEOUT" for row in outcomes) / total, 4),
        "schema_valid_rate": round(sum(row["metrics"]["schema_valid"] for row in outcomes) / total, 4),
        "product_detection_rate": round(sum(row["metrics"]["product_detected"] for row in outcomes) / total, 4),
        "module_detection_rate": round(sum(row["metrics"]["module_detected"] for row in outcomes) / total, 4),
        "overlap_violation_rate": round(sum(row["error_code"] == "MODULE_OVERLAP" for row in outcomes) / total, 4),
    }
    is_passed = aggregate["pass_rate"] >= float(validator.get("minimum_pass_rate", 0.8))
    finished = dt.datetime.utcnow()
    run.run_status = "passed" if is_passed else "failed"
    run.aggregate_json = _json(aggregate)
    run.finished_at = finished
    run.elapsed_ms = max(0, int((finished - now).total_seconds() * 1000))
    if dataset_split == "calibration":
        dataset.status = "calibration_passed" if is_passed else "gt_ready"
        runtime.status = "calibration_passed" if is_passed else "draft"
    else:
        dataset.status = "passed" if is_passed else "failed"
        if is_passed:
            runtime.status = "holdout_passed"
    db.commit()
    db.refresh(run)
    return run


def run_to_dict(run: models.AnalysisEvaluationRun, *, include_details: bool, db: Session) -> dict:
    result = {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "dataset_split": run.dataset_split,
        "run_status": run.run_status,
        "aggregate": _load(run.aggregate_json, {}),
        "version_snapshot": _load(run.version_snapshot_json, {}),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "elapsed_ms": run.elapsed_ms,
        "unsealed": bool(run.unsealed_at),
    }
    if include_details:
        rows = (
            db.query(models.AnalysisEvaluationResult)
            .filter(models.AnalysisEvaluationResult.run_id == run.id)
            .all()
        )
        result["results"] = [{
            "id": row.id, "item_id": row.item_id, "status": row.status,
            "error_code": row.error_code, "metrics": _load(row.metrics_json, {}),
            "prediction": _load(row.prediction_json, {}), "elapsed_ms": row.elapsed_ms,
        } for row in rows]
    return result


def retry_result(
    db: Session,
    result: models.AnalysisEvaluationResult,
    *,
    actor: str,
) -> dict:
    if result.status != "failed":
        raise EvaluationConflict("只有失败项可以单条重试")
    run = db.get(models.AnalysisEvaluationRun, result.run_id)
    item = db.get(models.AnalysisEvaluationItem, result.item_id)
    if not run or not item or run.dataset_split != "calibration":
        raise EvaluationConflict("仅 Calibration 失败项允许单条重试")
    runtime = db.get(models.AnalysisRuntimeVersion, run.runtime_version_id)
    if not runtime:
        raise EvaluationConflict("运行版本不存在")
    outcome = evaluate_item(db, item, _load(runtime.validator_config_json, {}))
    result.status = outcome["status"]
    result.error_code = outcome["error_code"]
    result.metrics_json = _json(outcome["metrics"])
    result.prediction_json = _json({
        **outcome["prediction"], "retried_by": actor,
        "retried_at": dt.datetime.utcnow().isoformat(),
    })
    db.commit()
    return {
        "id": result.id,
        "item_id": result.item_id,
        "status": result.status,
        "error_code": result.error_code,
        "metrics": _load(result.metrics_json, {}),
        "prediction": _load(result.prediction_json, {}),
    }
