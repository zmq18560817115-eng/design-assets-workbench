"""Deterministic business-requirement layout retrieval and evaluation.

This module never reads PreferenceEvent or company-preference weights. Reasons
are produced only from persisted requirement, pattern, case and blueprint data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from . import config, crud, models
from .business_taxonomy import normalize_business_value, values_match
from .agents import run_pipeline
from .layout_patterns import (
    module_type_counts,
    normalize_module_type,
    structure_similarity,
)
from .vision_provider import analyze, analyze_layout_regions

SCORING_VERSION = "layout-search-rules-v1"
REFERENCE_PROMPT_VERSION = "requirement-reference-layout-v1"
REFERENCE_ANALYZER_VERSION = "reference-layout-v2"
WEIGHTS = {
    "business_scene": 35.0,
    "required_modules": 25.0,
    "layout_structure": 20.0,
    "information_density": 10.0,
    "visual_style": 5.0,
    "verification": 5.0,
}


def _loads(value: str | None, default):
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _list(value: str | None) -> list:
    parsed = _loads(value, [])
    return parsed if isinstance(parsed, list) else []


def normalized_module_counts(modules: list[dict] | list[str]) -> Counter[str]:
    if not modules:
        return Counter()
    if isinstance(modules[0], str):
        return Counter(normalize_module_type(str(value)) for value in modules)
    return module_type_counts(modules)  # type: ignore[arg-type]


def _contains(actual: str, expected: str) -> bool:
    actual, expected = (actual or "").strip().lower(), (expected or "").strip().lower()
    return bool(actual and expected and (expected in actual or actual in expected))


def _module_labels(counts: Counter[str]) -> list[str]:
    labels = {
        "main_title": "主标题区域",
        "product_image": "产品主体区域",
        "selling_point": "卖点信息区域",
        "parameter_table": "参数区域",
        "cta": "行动引导区域",
        "person_image": "人物区域",
        "scene_image": "场景区域",
    }
    return [labels.get(key, key) for key in sorted(counts)]


def _score_ratio(matches: list[bool], weight: float) -> float:
    # An omitted constraint is neutral: callers simply do not append it.
    return weight if not matches else weight * sum(matches) / len(matches)


def _blueprint_namespace(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        modules_json=json.dumps(data.get("modules_json") or [], ensure_ascii=False),
        module_count=len(data.get("modules_json") or []),
        grid_columns=int(data.get("grid_columns") or 1),
        grid_rows=int(data.get("grid_rows") or 1),
        reading_flow=data.get("reading_flow") or "",
        layout_signature=data.get("layout_signature") or "",
        orientation=data.get("orientation") or "square",
        canvas_ratio=data.get("canvas_ratio") or "1:1",
        information_density=data.get("information_density") or "medium",
    )


def _resolve_reference_path(image_path: str) -> Path:
    value = (image_path or "").strip()
    if value.startswith("/uploads/"):
        return config.UPLOAD_DIR / Path(value).name
    path = Path(value)
    return path if path.is_absolute() else config.UPLOAD_DIR / path.name


def _temporary_reference_blueprint(image_path: str) -> dict[str, Any]:
    path = _resolve_reference_path(image_path)
    features = analyze(str(path))
    regions = analyze_layout_regions(str(path))
    row_bands = regions.get("row_bands") or []
    modules: list[dict[str, Any]] = []
    types = ["main_title", "product_image", "selling_point", "cta"]
    for index, band in enumerate(row_bands[:4]):
        y1, y2 = band
        modules.append({
            "id": f"{types[index]}-1",
            "type": types[index],
            "label": types[index],
            "x": 0.06,
            "y": round(max(0.0, y1), 4),
            "width": 0.88,
            "height": round(max(0.03, min(1.0 - y1, y2 - y1)), 4),
            "priority": index + 1,
            "importance": 1,
            "alignment": "center",
            "description": "",
            "content_summary": "",
            "confidence": 0.65,
        })
    if not modules:
        modules = [{
            "id": "product_image-1", "type": "product_image",
            "label": "product_image", "x": .1, "y": .1,
            "width": .8, "height": .8, "priority": 1, "importance": 1,
            "alignment": "center", "description": "",
            "content_summary": "", "confidence": .4,
        }]
    ratio = (
        "1:1" if features.orientation == "square"
        else "16:9" if features.orientation == "landscape"
        else "3:4"
    )
    density = (
        "high" if features.text_density >= .18
        else "low" if features.text_density < .08
        else "medium"
    )
    return {
        "canvas_ratio": ratio,
        "orientation": features.orientation,
        "grid_columns": max(1, min(24, features.col_groups or 1)),
        "grid_rows": max(1, min(24, features.row_blocks or len(modules))),
        "reading_flow": (
            "left-to-right" if features.orientation == "landscape"
            else "top-to-bottom"
        ),
        "information_density": density,
        "layout_signature": (
            f"reference:{features.orientation}:{features.col_groups}:"
            f"{features.row_blocks}:{density}"
        ),
        "modules_json": modules,
    }


def _model_reference_blueprint(image_path: str) -> dict[str, Any]:
    path = _resolve_reference_path(image_path)
    result = run_pipeline(
        str(path), asset_category="layout", enable_vlm=True, strict_vlm=True
    )
    payload = crud.build_initial_layout_blueprint(
        SimpleNamespace(url=path.name), result
    )
    return payload.model_dump()


def analyze_reference(
    db: Session,
    requirement: models.BusinessRequirement,
    *,
    reanalyze: bool = False,
) -> models.RequirementReferenceAnalysis | None:
    if not requirement.reference_image_path:
        return None
    path = _resolve_reference_path(requirement.reference_image_path)
    try:
        image_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        image_sha256 = ""
    cached = (
        db.query(models.RequirementReferenceAnalysis)
        .filter(
            models.RequirementReferenceAnalysis.requirement_id == requirement.id,
            models.RequirementReferenceAnalysis.image_sha256 == image_sha256,
            models.RequirementReferenceAnalysis.analyzer_version
            == REFERENCE_ANALYZER_VERSION,
        )
        .order_by(models.RequirementReferenceAnalysis.id.desc())
        .first()
    )
    if cached and not reanalyze:
        return cached
    model_failure = ""
    try:
        if config.vlm_enabled():
            try:
                blueprint = _model_reference_blueprint(
                    requirement.reference_image_path
                )
                generation_mode = "model"
                model_name = config.VISION_MODEL
            except Exception as exc:
                model_failure = str(exc)[:1000]
                blueprint = _temporary_reference_blueprint(
                    requirement.reference_image_path
                )
                generation_mode = "deterministic_local"
                model_name = "pillow-layout-features"
        else:
            blueprint = _temporary_reference_blueprint(requirement.reference_image_path)
            generation_mode = "deterministic_local"
            model_name = "pillow-layout-features"
        row = models.RequirementReferenceAnalysis(
            requirement_id=requirement.id,
            image_path=requirement.reference_image_path,
            blueprint_json=json.dumps(blueprint, ensure_ascii=False),
            model_name=model_name,
            prompt_version=REFERENCE_PROMPT_VERSION,
            generation_mode=generation_mode,
            failure_reason=model_failure,
            image_sha256=image_sha256,
            analyzer_version=REFERENCE_ANALYZER_VERSION,
            analysis_status="completed",
        )
    except Exception as exc:
        row = models.RequirementReferenceAnalysis(
            requirement_id=requirement.id,
            image_path=requirement.reference_image_path,
            blueprint_json="{}",
            model_name="reference-analysis-fallback",
            prompt_version=REFERENCE_PROMPT_VERSION,
            generation_mode="failed_fallback",
            failure_reason=str(exc)[:1000],
            image_sha256=image_sha256,
            analyzer_version=REFERENCE_ANALYZER_VERSION,
            analysis_status="failed",
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _latest_case_blueprints(
    db: Session, include_unverified: bool,
) -> list[tuple[models.Case, models.LayoutBlueprint, bool]]:
    rows = (
        db.query(models.LayoutBlueprint)
        .join(models.Case, models.Case.id == models.LayoutBlueprint.case_id)
        .order_by(
            models.LayoutBlueprint.case_id,
            models.LayoutBlueprint.version.desc(),
            models.LayoutBlueprint.id.desc(),
        )
        .all()
    )
    latest_any: dict[int, models.LayoutBlueprint] = {}
    latest_verified: dict[int, models.LayoutBlueprint] = {}
    for row in rows:
        latest_any.setdefault(row.case_id, row)
        if row.review_status == "verified":
            latest_verified.setdefault(row.case_id, row)
    result = []
    for case_id, latest in latest_any.items():
        selected = latest_verified.get(case_id)
        if selected:
            result.append((selected.case, selected, True))
        elif include_unverified:
            result.append((latest.case, latest, False))
    return result


def _candidate_fields(
    result_type: str,
    source: models.LayoutPattern | models.Case,
    blueprint: models.LayoutPattern | models.LayoutBlueprint,
) -> dict[str, Any]:
    if result_type == "pattern":
        pattern = source
        return {
            "product_category": " ".join(_list(pattern.product_category_tags_json)),
            "channel": " ".join(_list(pattern.channel_tags)),
            "content_purpose": " ".join(_list(pattern.content_purpose_tags_json)),
            "campaign_stage": " ".join(
                _list(pattern.campaign_stage_tags_json) or _list(pattern.scene_tags)
            ),
            "business_goal": " ".join(_list(pattern.business_goal_tags)),
            "target_audience": pattern.usage_notes or "",
            "style_text": " ".join(
                _list(pattern.industry_tags)
                + _list(pattern.scene_tags)
                + [pattern.description or "", pattern.usage_notes or ""]
            ),
        }
    case = source
    analysis_style = ""
    if case.analysis:
        analysis_style = case.analysis.style or ""
    return {
        "product_category": case.product_category or "",
        "channel": case.channel or "",
        "content_purpose": case.content_type or "",
        "campaign_stage": case.campaign_stage or case.scene or "",
        "business_goal": case.business_goal or case.summary or "",
        "target_audience": case.summary or "",
        "style_text": analysis_style + " " + " ".join(tag.name for tag in case.tags),
    }


def _score_candidate(
    requirement: models.BusinessRequirement,
    *,
    result_type: str,
    source: models.LayoutPattern | models.Case,
    blueprint: models.LayoutPattern | models.LayoutBlueprint,
    verified: bool,
    reference_blueprint: dict[str, Any] | None,
    related_pattern_ids: list[int],
) -> tuple[dict[str, Any], list[str]]:
    modules = _list(blueprint.module_structure_json if result_type == "pattern"
                    else blueprint.modules_json)
    if not modules and result_type == "pattern":
        modules = _list(blueprint.modules_json)
    counts = normalized_module_counts(modules)
    required = [normalize_module_type(value) for value in _list(
        requirement.required_modules_json
    )]
    forbidden = [normalize_module_type(value) for value in _list(
        requirement.forbidden_modules_json
    )]
    forbidden_hits = sorted({value for value in forbidden if counts[value] > 0})

    fields = _candidate_fields(result_type, source, blueprint)
    scene_checks: list[bool] = []
    scene_labels: list[str] = []
    for key, label in (
        ("product_category", "产品品类"),
        ("channel", "渠道"),
        ("content_purpose", "内容目的"),
        ("campaign_stage", "投放阶段"),
        ("business_goal", "业务目标"),
        ("target_audience", "目标人群"),
    ):
        expected = getattr(requirement, key, "") or ""
        if expected:
            if key in {
                "product_category", "channel", "content_purpose", "campaign_stage"
            }:
                candidates = fields[key].split()
                matched = any(values_match(key, value, expected) for value in candidates)
            else:
                matched = _contains(fields[key], expected)
            scene_checks.append(matched)
            if matched:
                normalized = (
                    normalize_business_value(key, expected)
                    if key in {
                        "product_category", "channel", "content_purpose",
                        "campaign_stage",
                    } else expected
                )
                scene_labels.append(f"{label}匹配（标准值：{normalized}）")
    reference_ids = set(_list(
        requirement.reference_case_ids_json or requirement.reference_case_ids
    ))
    source_case_ids = (
        set(_list(source.evidence_case_ids_json or source.source_case_ids))
        if result_type == "pattern" else {source.id}
    )
    explicit_reference = bool(reference_ids & source_case_ids)
    business_scene = _score_ratio(scene_checks, WEIGHTS["business_scene"])
    if explicit_reference:
        business_scene = min(WEIGHTS["business_scene"], business_scene + 5)
        scene_labels.append("需求指定参考案例")

    matched_required = sorted({value for value in required if counts[value] > 0})
    missing_required = sorted(set(required) - set(matched_required))
    required_score = (
        WEIGHTS["required_modules"]
        if not required else
        WEIGHTS["required_modules"] * len(matched_required) / len(set(required))
    )

    layout_checks: list[bool] = []
    risks: list[str] = []
    adaptation: list[str] = []
    if requirement.orientation:
        same = blueprint.orientation == requirement.orientation
        layout_checks.append(same)
        if not same:
            risks.append(
                f"画布方向不一致：需求为{requirement.orientation}，"
                f"结果为{blueprint.orientation}"
            )
    if requirement.canvas_ratio:
        same = blueprint.canvas_ratio == requirement.canvas_ratio
        layout_checks.append(same)
        if not same:
            risks.append(
                f"画布比例适配风险：需求为{requirement.canvas_ratio}，"
                f"结果为{blueprint.canvas_ratio}"
            )
    reference_similarity = None
    if reference_blueprint:
        reference_similarity = structure_similarity(
            _blueprint_namespace(reference_blueprint), blueprint
        )
    layout_score = (
        WEIGHTS["layout_structure"]
        if not layout_checks and reference_similarity is None
        else WEIGHTS["layout_structure"] * (
            (
                sum(layout_checks)
                + (reference_similarity["total"] if reference_similarity else 0)
            )
            / (len(layout_checks) + (1 if reference_similarity else 0))
        )
    )

    density_score = WEIGHTS["information_density"]
    if requirement.information_density:
        density_score = (
            WEIGHTS["information_density"]
            if blueprint.information_density == requirement.information_density
            else 0.0
        )
        if not density_score:
            adaptation.append(
                f"信息密度需由{blueprint.information_density or '未知'}"
                f"调整为{requirement.information_density}"
            )

    style_keywords = _list(requirement.style_keywords_json)
    style_score = (
        WEIGHTS["visual_style"] if not style_keywords else
        WEIGHTS["visual_style"] * sum(
            _contains(fields["style_text"], keyword) for keyword in style_keywords
        ) / len(style_keywords)
    )
    verification_score = WEIGHTS["verification"] if verified else 0.0

    breakdown = {
        "business_scene": round(business_scene, 2),
        "required_modules": round(required_score, 2),
        "layout_structure": round(layout_score, 2),
        "information_density": round(density_score, 2),
        "visual_style": round(style_score, 2),
        "verification": round(verification_score, 2),
    }
    total = round(sum(breakdown.values()), 2)
    reasons = list(scene_labels)
    if requirement.orientation and blueprint.orientation == requirement.orientation:
        reasons.append("画布方向一致")
    if requirement.canvas_ratio and blueprint.canvas_ratio == requirement.canvas_ratio:
        reasons.append("画布比例一致")
    if matched_required:
        reasons.append("包含明确要求的模块：" + "、".join(matched_required))
    if reference_similarity:
        reasons.append(
            f"参考图片结构相似度{reference_similarity['total'] * 100:.0f}%"
        )
    reasons.append("人工确认排版证据" if verified else "未确认补充结果")
    if missing_required:
        adaptation.append("需要补充必需模块：" + "、".join(missing_required))
    if forbidden_hits:
        risks.append("命中禁止模块：" + "、".join(forbidden_hits))

    item_id = source.id
    source_case_ids_list = sorted(int(value) for value in source_case_ids)
    source_blueprint_ids = (
        _list(source.evidence_blueprint_ids_json or source.source_blueprint_ids)
        if result_type == "pattern" else [blueprint.id]
    )
    result = {
        "id": item_id,
        "name": source.name,
        "result_type": result_type,
        "total_score": total,
        "score_breakdown": breakdown,
        "match_reasons": reasons,
        "matched_required_modules": matched_required,
        "missing_required_modules": missing_required,
        "reusable_modules": _module_labels(counts),
        "adaptation_needed": adaptation,
        "risks": risks,
        "source_case_ids": source_case_ids_list,
        "source_blueprint_ids": [int(value) for value in source_blueprint_ids],
        "related_pattern_ids": related_pattern_ids,
        "review_status": source.review_status if result_type == "pattern"
                         else blueprint.review_status,
        "rank": 0,
    }
    return result, forbidden_hits


def run_search(
    db: Session,
    requirement: models.BusinessRequirement,
    *,
    pattern_limit: int = 10,
    case_limit: int = 20,
    include_unverified: bool = False,
    reanalyze_reference: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    reference_row = analyze_reference(
        db, requirement, reanalyze=reanalyze_reference
    )
    reference_blueprint = (
        _loads(reference_row.blueprint_json, {})
        if reference_row and reference_row.generation_mode != "failed_fallback"
        else None
    )

    verified_patterns = (
        db.query(models.LayoutPattern)
        .filter(models.LayoutPattern.review_status == "verified")
        .order_by(models.LayoutPattern.id)
        .all()
    )
    pattern_results, excluded = [], []
    for pattern in verified_patterns:
        item, forbidden = _score_candidate(
            requirement, result_type="pattern", source=pattern,
            blueprint=pattern, verified=True,
            reference_blueprint=reference_blueprint,
            related_pattern_ids=[pattern.id],
        )
        (excluded if forbidden else pattern_results).append(item)

    case_results = []
    for case, blueprint, verified in _latest_case_blueprints(
        db, include_unverified
    ):
        related = [
            pattern.id for pattern in verified_patterns
            if case.id in set(_list(
                pattern.evidence_case_ids_json or pattern.source_case_ids
            ))
        ]
        item, forbidden = _score_candidate(
            requirement, result_type="case", source=case,
            blueprint=blueprint, verified=verified,
            reference_blueprint=reference_blueprint,
            related_pattern_ids=related,
        )
        (excluded if forbidden else case_results).append(item)

    def ranked(items: list[dict], limit: int) -> list[dict]:
        items.sort(key=lambda value: (-value["total_score"], value["id"]))
        selected = items[:limit]
        for rank, item in enumerate(selected, 1):
            item["rank"] = rank
        return selected

    patterns = ranked(pattern_results, pattern_limit)
    cases = ranked(case_results, case_limit)
    excluded.sort(key=lambda value: (value["result_type"], value["id"]))
    for rank, item in enumerate(excluded, 1):
        item["rank"] = rank
    elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
    constraints = {
        "required_modules": _list(requirement.required_modules_json),
        "forbidden_modules": _list(requirement.forbidden_modules_json),
        "canvas_ratio": requirement.canvas_ratio or None,
        "orientation": requirement.orientation or None,
        "information_density": requirement.information_density or None,
        "include_unverified": include_unverified,
    }
    result_snapshot = {
        "patterns": patterns,
        "cases": cases,
        "excluded_results": excluded,
        "constraints_applied": constraints,
        "search_summary": {
            "pattern_count": len(patterns),
            "case_count": len(cases),
            "excluded_count": len(excluded),
            "elapsed_ms": elapsed_ms,
            "reference_analysis": (
                {
                    "id": reference_row.id,
                    "generation_mode": reference_row.generation_mode,
                    "model_name": reference_row.model_name,
                    "prompt_version": reference_row.prompt_version,
                    "failure_reason": reference_row.failure_reason,
                    "image_sha256": reference_row.image_sha256,
                    "analyzer_version": reference_row.analyzer_version,
                    "analysis_status": reference_row.analysis_status,
                    "verified_by": reference_row.verified_by,
                    "verified_at": reference_row.verified_at,
                } if reference_row else None
            ),
        },
        "scoring_version": SCORING_VERSION,
    }
    run = models.LayoutSearchRun(
        requirement_id=requirement.id,
        query_snapshot_json=json.dumps(
            crud.serialize_business_requirement(requirement),
            ensure_ascii=False,
            default=str,
        ),
        result_snapshot_json=json.dumps(
            result_snapshot, ensure_ascii=False, default=str
        ),
        scoring_version=SCORING_VERSION,
        reference_analysis_id=reference_row.id if reference_row else None,
        elapsed_ms=elapsed_ms,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {
        "requirement": crud.serialize_business_requirement(requirement),
        "search_run_id": run.id,
        **result_snapshot,
    }


def latest_search(
    db: Session, requirement: models.BusinessRequirement,
) -> dict[str, Any] | None:
    run = (
        db.query(models.LayoutSearchRun)
        .filter(models.LayoutSearchRun.requirement_id == requirement.id)
        .order_by(models.LayoutSearchRun.id.desc())
        .first()
    )
    if not run:
        return None
    return {
        "requirement": crud.serialize_business_requirement(requirement),
        "search_run_id": run.id,
        **_loads(run.result_snapshot_json, {}),
    }


def add_feedback(
    db: Session,
    run: models.LayoutSearchRun,
    *,
    result_type: str,
    result_id: int,
    rank: int,
    relevance: str,
    reviewer: str,
    notes: str = "",
) -> models.LayoutSearchFeedback:
    snapshot = _loads(run.result_snapshot_json, {})
    rows = snapshot.get("patterns" if result_type == "pattern" else "cases", [])
    expected = next(
        (row for row in rows if row.get("id") == result_id), None
    )
    if not expected or expected.get("rank") != rank:
        raise ValueError("反馈结果或排名不属于该检索运行")
    row = models.LayoutSearchFeedback(
        search_run_id=run.id,
        requirement_id=run.requirement_id,
        result_type=result_type,
        result_id=result_id,
        rank=rank,
        relevance=relevance,
        reviewer=reviewer.strip(),
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def legacy_feedback_evaluation(db: Session) -> dict[str, Any]:
    feedback = (
        db.query(models.LayoutSearchFeedback)
        .order_by(models.LayoutSearchFeedback.id)
        .all()
    )
    latest: dict[tuple[int, str, int], models.LayoutSearchFeedback] = {}
    for row in feedback:
        latest[(row.search_run_id, row.result_type, row.result_id)] = row
    rows = list(latest.values())
    relevant_values = {"relevant", "partially_relevant"}

    def precision(limit: int) -> tuple[int, float]:
        judged = [row for row in rows if row.rank <= limit]
        relevant = sum(row.relevance in relevant_values for row in judged)
        return relevant, round(relevant / len(judged), 4) if judged else 0.0

    top5_count, precision5 = precision(5)
    top10_count, precision10 = precision(10)
    runs = db.query(models.LayoutSearchRun).all()
    violations = 0
    for run in runs:
        snapshot = _loads(run.result_snapshot_json, {})
        for row in snapshot.get("patterns", []) + snapshot.get("cases", []):
            if any("命中禁止模块" in risk for risk in row.get("risks", [])):
                violations += 1
    return {
        "evaluated_requirement_count": len({row.requirement_id for row in rows}),
        "evaluated_result_count": len(rows),
        "top5_relevant_count": top5_count,
        "top10_relevant_count": top10_count,
        "precision_at_5": precision5,
        "precision_at_10": precision10,
        "forbidden_module_violation_count": violations,
        "average_search_elapsed_ms": (
            round(sum(run.elapsed_ms or 0 for run in runs) / len(runs), 2)
            if runs else 0.0
        ),
    }


def _ground_truth_dict(row: models.LayoutSearchGroundTruth) -> dict[str, Any]:
    return {key: getattr(row, key) for key in (
        "id", "requirement_id", "result_type", "result_id",
        "expected_relevance", "reviewer", "reason", "dataset_version",
        "dataset_split", "frozen_at", "created_at",
    )}


def _dataset_dict(db: Session, row: models.LayoutSearchDataset) -> dict[str, Any]:
    truth = db.query(models.LayoutSearchGroundTruth).filter(
        models.LayoutSearchGroundTruth.dataset_version == row.dataset_version
    ).all()
    requirement_ids = {item.requirement_id for item in truth}
    return {
        "id": row.id, "dataset_version": row.dataset_version, "name": row.name,
        "description": row.description, "dataset_kind": row.dataset_kind,
        "created_by": row.created_by, "frozen_at": row.frozen_at,
        "last_run_at": row.last_run_at, "created_at": row.created_at,
        "requirement_count": len(requirement_ids), "annotation_count": len(truth),
        "calibration_requirement_count": len({
            item.requirement_id for item in truth
            if item.dataset_split == "calibration"
        }),
        "holdout_requirement_count": len({
            item.requirement_id for item in truth if item.dataset_split == "holdout"
        }),
    }


def create_dataset(db: Session, **values: Any):
    values["dataset_version"] = values["dataset_version"].strip()
    if db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == values["dataset_version"]
    ).first():
        raise ValueError("数据集版本已存在")
    row = models.LayoutSearchDataset(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dataset_dict(db, row)


def list_datasets(db: Session):
    return [_dataset_dict(db, row) for row in db.query(
        models.LayoutSearchDataset
    ).order_by(models.LayoutSearchDataset.created_at.desc()).all()]


def list_ground_truth(db: Session, dataset_version: str | None = None):
    query = db.query(models.LayoutSearchGroundTruth)
    if dataset_version:
        query = query.filter(
            models.LayoutSearchGroundTruth.dataset_version == dataset_version
        )
    return [_ground_truth_dict(row) for row in query.order_by(
        models.LayoutSearchGroundTruth.dataset_version,
        models.LayoutSearchGroundTruth.requirement_id,
        models.LayoutSearchGroundTruth.result_type,
        models.LayoutSearchGroundTruth.result_id,
    )]


def create_ground_truth(db: Session, **values: Any):
    if not db.get(models.BusinessRequirement, values["requirement_id"]):
        raise ValueError("业务需求不存在")
    target = models.LayoutPattern if values["result_type"] == "pattern" else models.Case
    if not db.get(target, values["result_id"]):
        raise ValueError("Ground Truth 引用的结果不存在")
    dataset = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == values["dataset_version"]
    ).first()
    if not dataset:
        raise ValueError("数据集版本不存在，请先创建数据集")
    if dataset.frozen_at or db.query(models.LayoutSearchGroundTruth).filter(
        models.LayoutSearchGroundTruth.dataset_version == values["dataset_version"],
        models.LayoutSearchGroundTruth.frozen_at.isnot(None),
    ).first():
        raise ValueError("该数据集版本已冻结，不可修改；请创建新版本")
    row = models.LayoutSearchGroundTruth(**values)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("该结果在当前数据集版本中已标注") from None
    db.refresh(row)
    return _ground_truth_dict(row)


def freeze_ground_truth(db: Session, dataset_version: str):
    rows = db.query(models.LayoutSearchGroundTruth).filter(
        models.LayoutSearchGroundTruth.dataset_version == dataset_version
    ).all()
    if not rows:
        raise ValueError("该数据集版本没有 Ground Truth")
    dataset = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == dataset_version
    ).first()
    if not dataset:
        dataset = models.LayoutSearchDataset(
            dataset_version=dataset_version, name=dataset_version,
            description="兼容旧数据集", dataset_kind="fixture",
            created_by="legacy-migration",
        )
        db.add(dataset)
        db.flush()
    if all(row.frozen_at for row in rows):
        return {"dataset_version": dataset_version, "frozen_at": rows[0].frozen_at,
                "count": len(rows)}
    if any(row.frozen_at for row in rows):
        raise ValueError("数据集冻结状态不一致，请创建新版本")
    errors = []
    split_by_requirement: dict[int, set[str]] = {}
    types_by_requirement: dict[int, set[str]] = {}
    for row in rows:
        split_by_requirement.setdefault(row.requirement_id, set()).add(
            row.dataset_split
        )
        types_by_requirement.setdefault(row.requirement_id, set()).add(
            row.result_type
        )
        requirement = db.get(models.BusinessRequirement, row.requirement_id)
        if not requirement or requirement.status != "confirmed":
            errors.append(f"需求 #{row.requirement_id} 不是 confirmed")
        if not row.reviewer.strip():
            errors.append(f"标注 #{row.id} reviewer 为空")
        if not row.reason.strip():
            errors.append(f"标注 #{row.id} reason 为空")
    for requirement_id, splits in split_by_requirement.items():
        if len(splits) != 1:
            errors.append(f"需求 #{requirement_id} 同时属于多个 split")
        if types_by_requirement.get(requirement_id) != {"case", "pattern"}:
            errors.append(f"需求 #{requirement_id} 必须同时包含案例和模式标注")
    if errors:
        db.rollback()
        raise ValueError("冻结校验失败：" + "；".join(sorted(set(errors))))
    now = dt.datetime.utcnow()
    for row in rows:
        row.frozen_at = now
    dataset.frozen_at = now
    db.commit()
    return {"dataset_version": dataset_version, "frozen_at": now, "count": len(rows)}


def run_acceptance(
    db: Session, dataset_version: str, dataset_split: str | None = None,
):
    query = db.query(models.LayoutSearchGroundTruth).filter(
        models.LayoutSearchGroundTruth.dataset_version == dataset_version,
        models.LayoutSearchGroundTruth.frozen_at.isnot(None),
    )
    if dataset_split:
        query = query.filter(
            models.LayoutSearchGroundTruth.dataset_split == dataset_split
        )
    rows = query.all()
    if not rows:
        raise ValueError("没有已冻结的 Ground Truth；必须先冻结再运行验收")
    for requirement_id in sorted({row.requirement_id for row in rows}):
        run_search(
            db, db.get(models.BusinessRequirement, requirement_id),
            pattern_limit=10, case_limit=20, include_unverified=False,
            reanalyze_reference=False,
        )
    dataset = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == dataset_version
    ).first()
    if dataset:
        dataset.last_run_at = dt.datetime.utcnow()
        db.commit()
    return evaluation(db, dataset_version)


def _metric_block(db: Session, truth_rows):
    details = []
    for requirement_id in sorted({row.requirement_id for row in truth_rows}):
        truth = [row for row in truth_rows if row.requirement_id == requirement_id]
        frozen_at = max(row.frozen_at for row in truth if row.frozen_at)
        run = db.query(models.LayoutSearchRun).filter(
            models.LayoutSearchRun.requirement_id == requirement_id,
            models.LayoutSearchRun.created_at >= frozen_at,
        ).order_by(models.LayoutSearchRun.id.desc()).first()
        labels = {
            kind: {row.result_id: row.expected_relevance for row in truth
                   if row.result_type == kind}
            for kind in ("case", "pattern")
        }
        snapshot = _loads(run.result_snapshot_json, {}) if run else {}
        cases, patterns = snapshot.get("cases", []), snapshot.get("patterns", [])

        def precision(results, mapping, limit, useful=False):
            selected = results[:limit]
            weights = {
                "relevant": 1.0,
                "partially_relevant": 0.5 if useful else 0.0,
                "irrelevant": 0.0,
            }
            score = sum(weights.get(mapping.get(item["id"]), 0.0)
                        for item in selected)
            return {
                "value": round(score / limit, 4),
                "requested_k": limit,
                "returned_count": len(selected),
                "effective_denominator": limit,
                "weighted_relevance_sum": score,
            }

        relevant_cases = {key for key, value in labels["case"].items()
                          if value == "relevant"}
        returned_cases = {item["id"] for item in cases[:10]}
        all_results = cases + patterns
        known = sum(item["id"] in labels[kind]
                    for kind, values in (("case", cases), ("pattern", patterns))
                    for item in values)
        violations = sum(
            any("禁止模块" in risk for risk in item.get("risks", []))
            for item in all_results
        )
        traceable = sum(bool(item.get("source_case_ids")
                             or item.get("source_blueprint_ids"))
                        for item in all_results)
        case_direct = precision(cases, labels["case"], 5)
        case_useful = precision(cases, labels["case"], 10, True)
        pattern_direct = precision(patterns, labels["pattern"], 3)
        pattern_useful = precision(patterns, labels["pattern"], 5, True)
        details.append({
            "requirement_id": requirement_id,
            "dataset_split": truth[0].dataset_split,
            "search_run_id": run.id if run else None,
            "returned_case_count": len(cases),
            "returned_pattern_count": len(patterns),
            "ground_truth_count": len(truth),
            "ground_truth_coverage": round(known / len(all_results), 4)
            if all_results else 0.0,
            "case_direct_precision_at_5": case_direct["value"],
            "case_useful_precision_at_10": case_useful["value"],
            "case_recall_at_10": round(
                len(relevant_cases & returned_cases) / len(relevant_cases), 4
            ) if relevant_cases else 0.0,
            "pattern_direct_precision_at_3": pattern_direct["value"],
            "pattern_useful_precision_at_5": pattern_useful["value"],
            "precision_denominators": {
                "case_direct_precision_at_5": case_direct,
                "case_useful_precision_at_10": case_useful,
                "pattern_direct_precision_at_3": pattern_direct,
                "pattern_useful_precision_at_5": pattern_useful,
            },
            "forbidden_module_violation_count": violations,
            "traceability_rate": round(traceable / len(all_results), 4)
            if all_results else 0.0,
            "average_search_elapsed_ms": run.elapsed_ms if run else 0,
            "false_positives": {
                "case": [item["id"] for item in cases[:10]
                         if labels["case"].get(item["id"]) == "irrelevant"],
                "pattern": [item["id"] for item in patterns[:5]
                            if labels["pattern"].get(item["id"]) == "irrelevant"],
            },
            "false_negatives": {
                "case": sorted(relevant_cases - returned_cases),
                "pattern": sorted(
                    {key for key, value in labels["pattern"].items()
                     if value == "relevant"}
                    - {item["id"] for item in patterns[:5]}
                ),
            },
        })
    mean_keys = (
        "case_direct_precision_at_5", "case_useful_precision_at_10",
        "case_recall_at_10", "pattern_direct_precision_at_3",
        "pattern_useful_precision_at_5", "ground_truth_coverage",
        "traceability_rate", "average_search_elapsed_ms",
    )
    metrics = {key: round(sum(row[key] for row in details) / len(details), 4)
               if details else 0.0 for key in mean_keys}
    metrics.update({
        "requirement_count": len(details),
        "returned_case_count": sum(row["returned_case_count"] for row in details),
        "returned_pattern_count": sum(row["returned_pattern_count"] for row in details),
        "ground_truth_count": sum(row["ground_truth_count"] for row in details),
        "forbidden_module_violation_count": sum(
            row["forbidden_module_violation_count"] for row in details
        ),
    })
    return {"metrics": metrics, "requirements": details}


def acceptance_status(
    preparation_gates: dict[str, bool], metric_gates: dict[str, bool],
) -> str:
    if not all(preparation_gates.values()):
        return "not_ready"
    return "passed" if all(metric_gates.values()) else "failed"


def evaluation(db: Session, dataset_version: str | None = None):
    if not dataset_version:
        latest = db.query(models.LayoutSearchGroundTruth.dataset_version).order_by(
            models.LayoutSearchGroundTruth.created_at.desc()
        ).first()
        dataset_version = latest[0] if latest else None
    rows = db.query(models.LayoutSearchGroundTruth).filter(
        models.LayoutSearchGroundTruth.dataset_version == dataset_version
    ).all() if dataset_version else []
    if not rows:
        empty = _metric_block(db, [])
        return {
            "status": "not_ready", "dataset_version": dataset_version,
            "message": "尚未完成真实业务验收",
            "dataset": {"total": 0, "calibration": 0, "holdout": 0},
            "overall": empty, "calibration": empty, "holdout": empty, "gates": {},
        }
    calibration = _metric_block(
        db, [row for row in rows if row.dataset_split == "calibration"]
    )
    holdout = _metric_block(
        db, [row for row in rows if row.dataset_split == "holdout"]
    )
    overall = _metric_block(db, rows)
    hm = holdout["metrics"]
    dataset_row = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == dataset_version
    ).first()
    requirement_ids = {row.requirement_id for row in rows}
    calibration_ids = {
        row.requirement_id for row in rows if row.dataset_split == "calibration"
    }
    holdout_ids = {
        row.requirement_id for row in rows if row.dataset_split == "holdout"
    }
    verified_company_case_ids = {
        case_id for (case_id,) in db.query(models.LayoutBlueprint.case_id).join(
            models.Case, models.Case.id == models.LayoutBlueprint.case_id
        ).join(models.Image, models.Image.id == models.Case.image_id).filter(
            models.LayoutBlueprint.review_status == "verified",
            models.Image.source_type.in_(("company_published", "company_finished_asset")),
        ).distinct().all()
    }
    company_case_count = db.query(models.Case).join(
        models.Image, models.Image.id == models.Case.image_id
    ).filter(models.Image.source_type.in_(
        ("company_published", "company_finished_asset")
    )).count()
    verified_pattern_count = db.query(models.LayoutPattern).filter(
        models.LayoutPattern.review_status == "verified"
    ).count()
    confirmed_requirement_count = db.query(models.BusinessRequirement).filter(
        models.BusinessRequirement.status == "confirmed"
    ).count()
    enough = bool(holdout["requirements"]) and all(
        row["search_run_id"] and row["returned_case_count"] >= 10
        and row["returned_pattern_count"] >= 3
        for row in holdout["requirements"]
    )
    metric_gates = {
        "case_direct_precision_at_5": hm["case_direct_precision_at_5"] >= .60,
        "case_useful_precision_at_10": hm["case_useful_precision_at_10"] >= .60,
        "pattern_direct_precision_at_3": hm["pattern_direct_precision_at_3"] >= .67,
        "forbidden_module_violation_count":
            hm["forbidden_module_violation_count"] == 0,
        "traceability_rate": hm["traceability_rate"] == 1.0,
        "minimum_results_per_requirement": enough,
    }
    preparation_gates = {
        "real_dataset": bool(dataset_row and dataset_row.dataset_kind == "real"),
        "dataset_frozen": bool(
            dataset_row and dataset_row.frozen_at and all(row.frozen_at for row in rows)
        ),
        "evaluation_has_run": bool(
            dataset_row and dataset_row.last_run_at
            and all(item["search_run_id"] for item in overall["requirements"])
        ),
        "minimum_total_requirements": len(requirement_ids) >= 10,
        "minimum_calibration_requirements": len(calibration_ids) >= 7,
        "minimum_holdout_requirements": len(holdout_ids) >= 3,
        "minimum_verified_company_cases": len(verified_company_case_ids) >= 50,
        "minimum_verified_patterns": verified_pattern_count >= 5,
    }
    status = acceptance_status(preparation_gates, metric_gates)
    passed = status == "passed"
    gates = {**preparation_gates, **metric_gates}
    blockers = [key for key, value in gates.items() if not value]
    return {
        "status": status,
        "dataset_version": dataset_version,
        "message": "真实业务验收门禁通过" if passed else "尚未完成真实业务验收",
        "dataset": {
            "total": len(rows),
            "requirement_count": len(requirement_ids),
            "annotation_count": len(rows),
            "calibration": len(calibration_ids),
            "holdout": len(holdout_ids),
            "frozen": all(row.frozen_at for row in rows),
            "dataset_kind": dataset_row.dataset_kind if dataset_row else "unknown",
            "last_run_at": dataset_row.last_run_at if dataset_row else None,
        },
        "readiness": {
            "company_case_count": company_case_count,
            "verified_blueprint_case_count": len(verified_company_case_ids),
            "verified_blueprint_coverage": round(
                len(verified_company_case_ids) / company_case_count, 4
            ) if company_case_count else 0.0,
            "verified_pattern_count": verified_pattern_count,
            "confirmed_requirement_count": confirmed_requirement_count,
            "ground_truth_coverage": overall["metrics"]["ground_truth_coverage"],
            "blocking_reasons": blockers,
            "can_enter_task_5": passed,
        },
        "overall": overall, "calibration": calibration,
        "holdout": holdout, "gates": gates,
    }
