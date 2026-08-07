"""Governed preparation and human labeling for real layout-search acceptance."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy.orm import Session

from . import layout_search, models

DATASET_VERSION = "real-search-acceptance-v1"
CALIBRATION_IDS = (1, 3, 4, 5, 6, 9, 10)
HOLDOUT_IDS = (2, 7, 8)
REVIEWER = "张茗淇"


class AcceptancePreparationError(ValueError):
    pass


def _verified_context_case_ids(db: Session) -> set[int]:
    return {
        row.case_id for row in db.query(models.CaseBusinessContext).filter_by(
            confirmation_status="verified"
        ).all()
    }


def prerequisites(db: Session) -> dict[str, Any]:
    confirmed_ids = {
        row.id for row in db.query(models.BusinessRequirement).filter_by(
            status="confirmed"
        ).all()
    }
    context_ids = _verified_context_case_ids(db)
    searchable_ids = {
        case.id for case, _blueprint, verified in layout_search._latest_case_blueprints(
            db, False, allowed_case_ids=context_ids
        ) if verified
    }
    patterns = layout_search._formal_verified_patterns(db)
    required_ids = set(CALIBRATION_IDS + HOLDOUT_IDS)
    gates = {
        "confirmed_requirements_exactly_10": confirmed_ids == required_ids,
        "verified_case_contexts_at_least_50": len(context_ids) >= 50,
        "searchable_company_cases_at_least_50": len(searchable_ids) >= 50,
        "verified_formal_patterns_at_least_5": len(patterns) >= 5,
    }
    return {
        "gates": gates,
        "confirmed_requirement_count": len(confirmed_ids),
        "verified_case_context_count": len(context_ids),
        "searchable_company_case_count": len(searchable_ids),
        "verified_formal_pattern_count": len(patterns),
        "searchable_case_ids": sorted(searchable_ids),
    }


def preview(db: Session) -> dict[str, Any]:
    checks = prerequisites(db)
    existing = db.query(models.LayoutSearchDataset).filter_by(
        dataset_version=DATASET_VERSION
    ).first()
    return {
        "mode": "dry-run",
        **{k: v for k, v in checks.items() if k != "searchable_case_ids"},
        "dataset_version": DATASET_VERSION,
        "calibration_requirement_ids": list(CALIBRATION_IDS),
        "holdout_requirement_count": len(HOLDOUT_IDS),
        "holdout_executed": False,
        "holdout_read": False,
        "will_create_dataset": existing is None,
        "will_run_calibration": 0 if existing else len(CALIBRATION_IDS),
    }


def prepare(db: Session) -> dict[str, Any]:
    checks = prerequisites(db)
    failed = [key for key, value in checks["gates"].items() if not value]
    if failed:
        raise AcceptancePreparationError("准备门禁未通过: " + ", ".join(failed))
    existing = db.query(models.LayoutSearchDataset).filter_by(
        dataset_version=DATASET_VERSION
    ).first()
    if existing:
        return acceptance_detail(db, existing)
    dataset = models.LayoutSearchDataset(
        dataset_version=DATASET_VERSION,
        name="真实业务检索验收 v1",
        description=(
            "固定10条真实需求；Calibration 7条用于人工判断；Holdout 3条保持封存。"
            f"检索版本={layout_search.SCORING_VERSION}；评分规则版本={layout_search.SCORING_VERSION}"
        ),
        dataset_kind="real",
        search_version=layout_search.SCORING_VERSION,
        scoring_version=layout_search.SCORING_VERSION,
        created_by=REVIEWER,
    )
    db.add(dataset)
    try:
        db.flush()
        for requirement_id in CALIBRATION_IDS:
            db.add(models.LayoutSearchDatasetRequirement(
                dataset_id=dataset.id,
                requirement_id=requirement_id,
                dataset_split="calibration",
                holdout_executed=False,
                holdout_read=False,
            ))
        for requirement_id in HOLDOUT_IDS:
            db.add(models.LayoutSearchDatasetRequirement(
                dataset_id=dataset.id,
                requirement_id=requirement_id,
                dataset_split="holdout",
                holdout_executed=False,
                holdout_read=False,
            ))
        db.flush()
        searchable_ids = set(checks["searchable_case_ids"])
        members = db.query(models.LayoutSearchDatasetRequirement).filter_by(
            dataset_id=dataset.id, dataset_split="calibration"
        ).order_by(models.LayoutSearchDatasetRequirement.requirement_id).all()
        for member in members:
            requirement = db.get(models.BusinessRequirement, member.requirement_id)
            result = layout_search.run_search(
                db, requirement, pattern_limit=3, case_limit=10,
                include_unverified=False, reanalyze_reference=False,
                allowed_case_ids=searchable_ids, strict_product_category=True,
                commit=False,
            )
            member.search_run_id = result["search_run_id"]
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(dataset)
    return acceptance_detail(db, dataset)


def _result_with_source(db: Session, item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    if item["result_type"] == "case":
        case = db.get(models.Case, item["id"])
        context = db.query(models.CaseBusinessContext).filter_by(case_id=case.id).first()
        result.update({
            "image_url": case.image.url if case and case.image else "",
            "product_category": case.product_category if case else "",
            "content_purpose": context.content_purpose if context else "",
            "page_role": context.page_role if context else "",
            "source_evidence": {
                "case_id": case.id if case else None,
                "image_id": case.image_id if case else None,
                "blueprint_ids": item.get("source_blueprint_ids", []),
                "pattern_ids": item.get("related_pattern_ids", []),
            },
        })
    else:
        pattern = db.get(models.LayoutPattern, item["id"])
        case_ids = item.get("source_case_ids", [])
        first_case = db.get(models.Case, case_ids[0]) if case_ids else None
        result.update({
            "image_url": first_case.image.url if first_case and first_case.image else "",
            "product_category": " / ".join(json.loads(pattern.product_category_tags_json or "[]")) if pattern else "",
            "source_evidence": {
                "pattern_id": pattern.id if pattern else None,
                "case_ids": case_ids,
                "blueprint_ids": item.get("source_blueprint_ids", []),
            },
        })
    return result


def acceptance_detail(db: Session, dataset: models.LayoutSearchDataset) -> dict[str, Any]:
    members = db.query(models.LayoutSearchDatasetRequirement).filter_by(
        dataset_id=dataset.id
    ).order_by(models.LayoutSearchDatasetRequirement.requirement_id).all()
    calibration = []
    for member in members:
        if member.dataset_split != "calibration":
            continue
        requirement = db.get(models.BusinessRequirement, member.requirement_id)
        run = db.get(models.LayoutSearchRun, member.search_run_id) if member.search_run_id else None
        snapshot = json.loads(run.result_snapshot_json or "{}") if run else {}
        feedback = db.query(models.LayoutSearchFeedback).filter_by(
            search_run_id=run.id
        ).order_by(models.LayoutSearchFeedback.id).all() if run else []
        calibration.append({
            "requirement": {
                "id": requirement.id, "title": requirement.title,
                "raw_requirement": requirement.raw_requirement,
                "product_category": requirement.product_category,
                "content_purpose": requirement.content_purpose,
                "page_role": requirement.page_role,
                "required_modules_json": json.loads(requirement.required_modules_json or "[]"),
                "forbidden_modules_json": json.loads(requirement.forbidden_modules_json or "[]"),
            },
            "search_run_id": run.id if run else None,
            "scoring_version": run.scoring_version if run else layout_search.SCORING_VERSION,
            "cases": [_result_with_source(db, row) for row in snapshot.get("cases", [])],
            "patterns": [_result_with_source(db, row) for row in snapshot.get("patterns", [])],
            "feedback": [{
                "id": row.id, "result_type": row.result_type,
                "result_id": row.result_id, "rank": row.rank,
                "relevance": row.relevance, "reviewer": row.reviewer,
                "notes": row.notes, "created_at": row.created_at,
            } for row in feedback],
        })
    holdout = [row for row in members if row.dataset_split == "holdout"]
    return {
        "dataset_version": dataset.dataset_version,
        "name": dataset.name,
        "scoring_version": layout_search.SCORING_VERSION,
        "created_at": dataset.created_at,
        "calibration_count": len(calibration),
        "holdout_count": len(holdout),
        "holdout_executed": any(row.holdout_executed for row in holdout),
        "holdout_read": any(row.holdout_read for row in holdout),
        "completed_count": sum(bool(item["feedback"]) for item in calibration),
        "calibration": calibration,
    }


def add_judgment(
    db: Session, dataset_version: str, *, requirement_id: int,
    result_type: str, result_id: int, relevance: str, reviewer: str,
    notes: str = "",
) -> dict[str, Any]:
    if not reviewer.strip():
        raise AcceptancePreparationError("人工判断必须填写审核人")
    dataset = db.query(models.LayoutSearchDataset).filter_by(
        dataset_version=dataset_version
    ).first()
    if not dataset:
        raise AcceptancePreparationError("验收数据集不存在")
    member = db.query(models.LayoutSearchDatasetRequirement).filter_by(
        dataset_id=dataset.id, requirement_id=requirement_id,
        dataset_split="calibration",
    ).first()
    if not member or not member.search_run_id:
        raise AcceptancePreparationError("该需求不属于可见的 Calibration 队列")
    run = db.get(models.LayoutSearchRun, member.search_run_id)
    if result_type == "none":
        result_id, rank = 0, 0
    else:
        snapshot = json.loads(run.result_snapshot_json or "{}")
        key = "patterns" if result_type == "pattern" else "cases"
        found = next((row for row in snapshot.get(key, []) if row.get("id") == result_id), None)
        if not found:
            raise AcceptancePreparationError("判断对象不属于该检索运行")
        rank = found["rank"]
    row = models.LayoutSearchFeedback(
        search_run_id=run.id, requirement_id=requirement_id,
        result_type=result_type, result_id=result_id, rank=rank,
        relevance=relevance, reviewer=reviewer.strip(), notes=notes,
    )
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "created_at": row.created_at}


def _expected_decision_keys(db: Session, dataset: models.LayoutSearchDataset) -> set[tuple[int, str, int]]:
    keys: set[tuple[int, str, int]] = set()
    members = db.query(models.LayoutSearchDatasetRequirement).filter_by(
        dataset_id=dataset.id, dataset_split="calibration"
    ).all()
    for member in members:
        run = db.get(models.LayoutSearchRun, member.search_run_id) if member.search_run_id else None
        snapshot = json.loads(run.result_snapshot_json or "{}") if run else {}
        case_rows, pattern_rows = snapshot.get("cases", []), snapshot.get("patterns", [])
        if not case_rows and not pattern_rows:
            keys.add((member.requirement_id, "none", 0))
            continue
        keys.update((member.requirement_id, "case", int(row["id"])) for row in case_rows)
        keys.update((member.requirement_id, "pattern", int(row["id"])) for row in pattern_rows)
    return keys


def submit_ground_truth(
    db: Session, dataset_version: str, *, reviewer: str,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atomically publish a complete human-reviewed calibration draft."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise AcceptancePreparationError("提交正式验收结果必须填写审核人")
    dataset = db.query(models.LayoutSearchDataset).filter_by(
        dataset_version=dataset_version
    ).first()
    if not dataset:
        raise AcceptancePreparationError("验收数据集不存在")
    if dataset.frozen_at:
        raise AcceptancePreparationError("验收数据集已冻结")
    expected = _expected_decision_keys(db, dataset)
    supplied = {
        (int(row["requirement_id"]), str(row["result_type"]), int(row["result_id"]))
        for row in decisions
    }
    if len(supplied) != len(decisions) or supplied != expected:
        missing = len(expected - supplied)
        extra = len(supplied - expected)
        raise AcceptancePreparationError(f"必须完成全部判断后提交（缺少{missing}项，多出{extra}项）")
    existing = db.query(models.LayoutSearchGroundTruth).filter_by(
        dataset_version=dataset_version
    ).all()
    decision_by_key = {
        (int(row["requirement_id"]), str(row["result_type"]), int(row["result_id"])): row
        for row in decisions
    }
    relevance_map = {
        "relevant": "relevant", "irrelevant": "irrelevant",
        "uncertain": "partially_relevant",
    }
    if existing:
        existing_keys = {(row.requirement_id, row.result_type, row.result_id) for row in existing}
        if existing_keys == expected and all(
            row.reviewer == reviewer
            and row.expected_relevance == relevance_map[decision_by_key[(row.requirement_id, row.result_type, row.result_id)]["relevance"]]
            for row in existing
        ):
            return {"created": 0, "total": len(existing), "idempotent": True}
        raise AcceptancePreparationError("该数据集已存在正式验收结果，禁止部分覆盖")
    try:
        for row in decisions:
            reason_parts = [str(value).strip() for value in row.get("reasons", []) if str(value).strip()]
            if str(row.get("notes", "")).strip():
                reason_parts.append(str(row["notes"]).strip())
            db.add(models.LayoutSearchGroundTruth(
                requirement_id=int(row["requirement_id"]),
                result_type=str(row["result_type"]), result_id=int(row["result_id"]),
                expected_relevance=relevance_map[str(row["relevance"])],
                reviewer=reviewer, reason="；".join(reason_parts),
                dataset_version=dataset_version, dataset_split="calibration",
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"created": len(decisions), "total": len(decisions), "idempotent": False}
