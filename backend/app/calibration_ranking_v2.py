"""Conservative, immutable reranking for the frozen real-search calibration set.

The v2 ranker never expands the v1 candidate pool.  It therefore cannot read
holdout requirements or silently turn an unseen candidate into a positive
label.  New/unlabelled items are retained as pending calibration labels.
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from . import models
from .business_taxonomy import values_match


SCORING_VERSION = "layout-search-ranking-v2"
DATASET_VERSION = "real-search-acceptance-v1"

_MULTI_TERMS = ("多品", "选购", "测评", "横评", "对比", "评测", "1v1")
_CAPACITY_TERMS = ("网格", "矩阵", "列表", "分栏", "对比", "横评", "测评", "多品")
_LOW_CAPACITY_TERMS = ("单品", "种草", "活动海报", "极简", "留白", "居中构图", "中轴型")
_PURPOSE_TERMS = ("对比", "横评", "测评", "评测", "选购", "攻略")


def _loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def requirement_scope(requirement: models.BusinessRequirement) -> dict[str, Any]:
    required = _loads(requirement.required_modules_json, [])
    text = " ".join(
        str(value or "")
        for value in (
            requirement.title,
            requirement.raw_requirement,
            requirement.content_purpose,
            requirement.page_role,
            " ".join(str(item) for item in required),
        )
    )
    numbers = [int(value) for value in re.findall(r"(?<!\d)(\d{1,2})(?:品|款|个)", text)]
    chinese = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    numbers.extend(value for key, value in chinese.items() if f"{key}品" in text or f"{key}款" in text)
    explicit_count = max(numbers, default=None)
    multi = bool(explicit_count and explicit_count > 1) or any(term in text for term in _MULTI_TERMS)
    high_information = multi or any(term in text for term in ("表格", "参数", "拆机", "科普", "信息"))
    return {"multi_product": multi, "explicit_product_count": explicit_count, "high_information": high_information}


def _case_capacity(case: models.Case, blueprint: models.LayoutBlueprint) -> tuple[int, list[str]]:
    modules = _loads(blueprint.modules_json, [])
    product_regions = sum(1 for item in modules if item.get("type") == "product_image")
    purpose_text = " ".join((case.name or "", case.content_type or "", case.scene or ""))
    text = purpose_text + " " + (case.summary or "")
    score = min(product_regions, 4) * 12
    reasons: list[str] = []
    purpose_hits = [term for term in _PURPOSE_TERMS if term in purpose_text]
    if purpose_hits:
        score += 80
        reasons.append("案例用途含" + "、".join(purpose_hits[:2]))
    hits = [term for term in _CAPACITY_TERMS if term in text]
    if hits:
        score += min(20, len(hits) * 5)
        reasons.append("结构含" + "、".join(hits[:3]))
    low_hits = [term for term in _LOW_CAPACITY_TERMS if term in text]
    if low_hits and not hits:
        if purpose_hits:
            score -= 15
        reasons.append("偏单品或低容量：" + "、".join(low_hits[:2]))
    if product_regions >= 2:
        reasons.append(f"产品区{product_regions}个")
    if blueprint.information_density == "high":
        score += 10
    return score, reasons


def _same_category(requirement: models.BusinessRequirement, candidate: models.Case | models.LayoutPattern) -> bool:
    if isinstance(candidate, models.Case):
        actual = candidate.product_category or ""
    else:
        actual = " ".join(_loads(candidate.product_category_tags_json, []))
    return bool(actual and requirement.product_category and values_match("product_category", actual, requirement.product_category))


def rerank_snapshot(
    db: Session,
    requirement: models.BusinessRequirement,
    snapshot: dict[str, Any],
    known_labels: set[tuple[str, int]],
) -> dict[str, Any]:
    """Rerank only the persisted v1 pool; do not discover new candidates."""
    result = copy.deepcopy(snapshot)
    scope = requirement_scope(requirement)
    excluded: list[dict[str, Any]] = list(result.get("excluded_results") or [])
    ranked_cases: list[dict[str, Any]] = []
    for item in result.get("cases") or []:
        case = db.get(models.Case, int(item["id"]))
        blueprint = None
        if case:
            blueprint = (
                db.query(models.LayoutBlueprint)
                .filter(models.LayoutBlueprint.case_id == case.id, models.LayoutBlueprint.review_status == "verified")
                .order_by(models.LayoutBlueprint.version.desc(), models.LayoutBlueprint.id.desc())
                .first()
            )
        if not case or not blueprint:
            excluded.append({"result_type": "case", "id": item.get("id"), "reason": "案例或verified蓝图不可追溯"})
            continue
        if not _same_category(requirement, case):
            excluded.append({"result_type": "case", "id": case.id, "reason": "产品品类不一致"})
            continue
        capacity, capacity_reasons = _case_capacity(case, blueprint)
        adjusted = float(item.get("total_score") or 0)
        deductions: list[str] = []
        if scope["multi_product"]:
            adjusted += capacity
            if capacity <= 0:
                adjusted -= 45
                deductions.append("多品需求，但现有结构缺少可信的对比或信息容量信号")
        item["v2_score"] = round(adjusted, 2)
        item["match_reasons"] = list(item.get("match_reasons") or []) + capacity_reasons
        item["deduction_reasons"] = deductions
        item["label_status"] = "frozen" if ("case", case.id) in known_labels else "pending_calibration_label"
        ranked_cases.append(item)
    ranked_cases.sort(key=lambda value: (-float(value["v2_score"]), int(value["id"])))
    for rank, item in enumerate(ranked_cases, 1):
        item["rank"] = rank

    patterns: list[dict[str, Any]] = []
    for item in result.get("patterns") or []:
        pattern = db.get(models.LayoutPattern, int(item["id"]))
        if not pattern or not _same_category(requirement, pattern):
            excluded.append({"result_type": "pattern", "id": item.get("id"), "reason": "产品品类不一致"})
            continue
        modules = _loads(pattern.modules_json or pattern.module_structure_json, [])
        product_regions = sum(1 for module in modules if module.get("type") == "product_image")
        missing = list(item.get("missing_required_modules") or [])
        if scope["multi_product"] and (product_regions < 2 or missing):
            excluded.append({
                "result_type": "pattern", "id": pattern.id,
                "reason": "正式模式无法同时承载多品范围、页面角色和必需信息",
            })
            continue
        item["label_status"] = "frozen" if ("pattern", pattern.id) in known_labels else "pending_calibration_label"
        patterns.append(item)
    for rank, item in enumerate(patterns, 1):
        item["rank"] = rank

    result["cases"] = ranked_cases[:10]
    result["patterns"] = patterns[:3]
    result["excluded_results"] = excluded
    result["scoring_version"] = SCORING_VERSION
    result["ranking_scope"] = scope
    result["pattern_empty_state"] = "暂无合适排版模式" if not patterns else ""
    result["pattern_knowledge_gap"] = (
        requirement.product_category if not patterns and requirement.product_category in {"恒温杯", "羊脂膏"} else ""
    )
    return result


def create_v2_runs(db: Session, *, dataset_version: str = DATASET_VERSION) -> dict[str, Any]:
    dataset = db.query(models.LayoutSearchDataset).filter_by(dataset_version=dataset_version).one()
    members = (
        db.query(models.LayoutSearchDatasetRequirement)
        .filter_by(dataset_id=dataset.id, dataset_split="calibration")
        .order_by(models.LayoutSearchDatasetRequirement.requirement_id)
        .all()
    )
    labels = db.query(models.LayoutSearchGroundTruth).filter_by(
        dataset_version=dataset_version, dataset_split="calibration"
    ).all()
    known = {(row.result_type, row.result_id) for row in labels if row.result_id > 0}
    created = 0
    runs: list[models.LayoutSearchRun] = []
    for member in members:
        existing = db.query(models.LayoutSearchRun).filter_by(
            requirement_id=member.requirement_id, scoring_version=SCORING_VERSION
        ).first()
        if existing:
            runs.append(existing)
            continue
        source = db.query(models.LayoutSearchRun).filter_by(
            requirement_id=member.requirement_id, scoring_version="layout-search-rules-v1"
        ).order_by(models.LayoutSearchRun.id.desc()).first()
        if not source:
            raise ValueError(f"requirement {member.requirement_id} has no frozen v1 run")
        requirement = db.get(models.BusinessRequirement, member.requirement_id)
        snapshot = rerank_snapshot(db, requirement, _loads(source.result_snapshot_json, {}), known)
        query = _loads(source.query_snapshot_json, {})
        query.update({"scoring_version": SCORING_VERSION, "source_run_id": source.id, "candidate_pool": "frozen_v1"})
        row = models.LayoutSearchRun(
            requirement_id=member.requirement_id,
            query_snapshot_json=json.dumps(query, ensure_ascii=False),
            result_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            scoring_version=SCORING_VERSION,
            reference_analysis_id=source.reference_analysis_id,
            elapsed_ms=0,
        )
        db.add(row)
        db.flush()
        runs.append(row)
        created += 1
    return {"created": created, "runs": runs, "label_count": len(labels)}


def metrics(db: Session, runs: list[models.LayoutSearchRun], *, dataset_version: str = DATASET_VERSION) -> dict[str, Any]:
    labels = db.query(models.LayoutSearchGroundTruth).filter_by(
        dataset_version=dataset_version, dataset_split="calibration"
    ).all()
    truth = {(row.requirement_id, row.result_type, row.result_id): row.expected_relevance for row in labels}
    case_labels: list[str] = []
    pattern_labels: list[str] = []
    top5: list[str] = []
    per_requirement: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for run in runs:
        snap = _loads(run.result_snapshot_json, {})
        cases = snap.get("cases") or []
        patterns = snap.get("patterns") or []
        for item in cases:
            label = truth.get((run.requirement_id, "case", int(item["id"])))
            if label: case_labels.append(label)
            else: pending.append({"requirement_id": run.requirement_id, "result_type": "case", "result_id": item["id"]})
        for item in cases[:5]:
            label = truth.get((run.requirement_id, "case", int(item["id"])))
            if label: top5.append(label)
        for item in patterns:
            label = truth.get((run.requirement_id, "pattern", int(item["id"])))
            if label: pattern_labels.append(label)
            else: pending.append({"requirement_id": run.requirement_id, "result_type": "pattern", "result_id": item["id"]})
        first = next((index for index,item in enumerate(cases,1) if truth.get((run.requirement_id,"case",int(item["id"]))) == "relevant"), None)
        per_requirement.append({"requirement_id": run.requirement_id, "case_count": len(cases), "pattern_count": len(patterns), "first_relevant_rank": first, "pattern_empty_state": snap.get("pattern_empty_state", "")})
    relevant = lambda values: sum(value == "relevant" for value in values)
    return {
        "scoring_version": SCORING_VERSION,
        "case_accuracy": round(relevant(case_labels) / len(case_labels), 4) if case_labels else None,
        "case_top5_accuracy": round(relevant(top5) / len(top5), 4) if top5 else None,
        "pattern_accuracy": round(relevant(pattern_labels) / len(pattern_labels), 4) if pattern_labels else None,
        "pattern_returned": len(pattern_labels),
        "pending_calibration_labels": pending,
        "requirements": per_requirement,
    }
