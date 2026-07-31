"""Deterministic, explainable LayoutPattern discovery.

This service deliberately ignores PreferenceEvent, training data, company
profile, service-run weights, colors and style frequency. Only the latest valid
verified LayoutBlueprint for each real case is eligible evidence.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session

from . import models
from .business_contract import is_company_evidence
from .business_taxonomy import normalize_business_value
from .layout_blueprint import validate_canvas_ratio, validate_modules

DEFAULT_SIMILARITY_THRESHOLD = 0.72
DEFAULT_MINIMUM_EVIDENCE = 3
DISCOVERY_METHOD = "automatic-rules-v2"
CORE_TYPES = {
    "main_title", "product_image", "person_image", "scene_image",
    "selling_point", "parameter_table", "feature_list", "cta",
}


def _loads(value: str | None, default):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _modules(blueprint: models.LayoutBlueprint) -> list[dict[str, Any]]:
    value = _loads(blueprint.modules_json, [])
    return value if isinstance(value, list) else []


def _valid_blueprint(blueprint: models.LayoutBlueprint) -> bool:
    try:
        validate_canvas_ratio(blueprint.canvas_ratio)
        modules = _modules(blueprint)
        validate_modules(modules, blueprint.module_count)
        if not 0 <= float(blueprint.text_image_ratio) <= 1:
            return False
    except (TypeError, ValueError):
        return False
    return True


def latest_verified_blueprints(db: Session) -> list[models.LayoutBlueprint]:
    """Return the latest legal verified company blueprint for each case."""
    rows = (
        db.query(models.LayoutBlueprint)
        .join(models.Case, models.Case.id == models.LayoutBlueprint.case_id)
        .join(models.Image, models.Image.id == models.Case.image_id)
        .filter(models.LayoutBlueprint.review_status == "verified")
        .order_by(
            models.LayoutBlueprint.case_id,
            models.LayoutBlueprint.version.desc(),
            models.LayoutBlueprint.id.desc(),
        )
        .all()
    )
    selected: dict[int, models.LayoutBlueprint] = {}
    for blueprint in rows:
        case = blueprint.case
        if (
            case
            and case.image
            and is_company_evidence(
                case.image.source_type or "", case.trust_status or ""
            )
            and blueprint.case_id not in selected
            and _valid_blueprint(blueprint)
        ):
            selected[blueprint.case_id] = blueprint
    return list(selected.values())


def normalize_module_type(value: str) -> str:
    """Remove only the deterministic trailing instance suffix."""
    head, separator, tail = str(value or "other").rpartition("-")
    return head if separator and tail.isdigit() and head else str(value or "other")


def module_type_counts(modules: list[dict[str, Any]]) -> Counter[str]:
    return Counter(normalize_module_type(item.get("type", "other")) for item in modules)


def _ordered_by_type(blueprint: models.LayoutBlueprint) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for module in _modules(blueprint):
        grouped[normalize_module_type(module.get("type", "other"))].append(module)
    for items in grouped.values():
        items.sort(key=lambda item: (float(item.get("y", 0)), float(item.get("x", 0))))
    return grouped


def _module_type_similarity(left: models.LayoutBlueprint, right: models.LayoutBlueprint) -> float:
    a, b = module_type_counts(_modules(left)), module_type_counts(_modules(right))
    keys = set(a) | set(b)
    return (
        sum(min(a[key], b[key]) for key in keys)
        / sum(max(a[key], b[key]) for key in keys)
        if keys else 1.0
    )


def _position_similarity(left: models.LayoutBlueprint, right: models.LayoutBlueprint) -> float:
    a, b = _ordered_by_type(left), _ordered_by_type(right)
    scores: list[float] = []
    for module_type in sorted(set(a) | set(b)):
        left_items, right_items = a.get(module_type, []), b.get(module_type, [])
        for first, second in zip(left_items, right_items):
            delta = sum(
                abs(float(first.get(key, 0)) - float(second.get(key, 0)))
                for key in ("x", "y", "width", "height")
            ) / 4
            scores.append(max(0.0, 1.0 - delta))
        # Every unpaired module contributes a zero instead of silently
        # disappearing from the position score.
        scores.extend([0.0] * abs(len(left_items) - len(right_items)))
    paired_score = sum(scores) / len(scores) if scores else 1.0
    left_total, right_total = len(_modules(left)), len(_modules(right))
    total_count_score = (
        min(left_total, right_total) / max(left_total, right_total)
        if max(left_total, right_total) else 1.0
    )
    return paired_score * 0.75 + total_count_score * 0.25


def structure_similarity(left: models.LayoutBlueprint, right: models.LayoutBlueprint) -> dict[str, float]:
    """Return weighted similarity components and total in the 0..1 interval."""
    module_types = _module_type_similarity(left, right)
    position_size = _position_similarity(left, right)
    grid_score = (
        (1.0 if left.grid_columns == right.grid_columns else 0.35)
        + (1.0 if left.grid_rows == right.grid_rows else 0.35)
        + (1.0 if left.reading_flow == right.reading_flow else 0.0)
        + (1.0 if left.layout_signature and left.layout_signature == right.layout_signature else 0.0)
    ) / 4
    canvas_density = (
        (1.0 if left.orientation == right.orientation else 0.0)
        + (1.0 if left.canvas_ratio == right.canvas_ratio else 0.0)
        + (1.0 if left.information_density == right.information_density else 0.0)
    ) / 3
    total = (
        module_types * 0.35
        + position_size * 0.35
        + grid_score * 0.15
        + canvas_density * 0.15
    )
    return {
        "module_types": round(module_types, 4),
        "position_size": round(position_size, 4),
        "grid_reading_flow": round(grid_score, 4),
        "canvas_density": round(canvas_density, 4),
        "total": round(total, 4),
    }


def _primary_key(blueprint: models.LayoutBlueprint) -> tuple[str, str, str]:
    return (
        blueprint.orientation,
        blueprint.canvas_ratio,
        blueprint.information_density,
    )


def _cluster(
    blueprints: list[models.LayoutBlueprint],
    threshold: float,
) -> list[list[models.LayoutBlueprint]]:
    """Greedy deterministic clustering within strict canvas buckets."""
    clusters: list[list[models.LayoutBlueprint]] = []
    for blueprint in sorted(blueprints, key=lambda item: item.id):
        best_index = None
        best_score = -1.0
        for index, group in enumerate(clusters):
            average = sum(
                structure_similarity(blueprint, member)["total"]
                for member in group
            ) / len(group)
            if average >= threshold and average > best_score:
                best_index, best_score = index, average
        if best_index is None:
            clusters.append([blueprint])
        else:
            clusters[best_index].append(blueprint)
    return clusters


def _indexed_modules(blueprint: models.LayoutBlueprint) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for module_type, items in _ordered_by_type(blueprint).items():
        for index, item in enumerate(items, 1):
            indexed[f"{module_type}-{index}"] = item
    return indexed


def _average_modules(group: list[models.LayoutBlueprint]) -> tuple[list[dict], list[str], list[str], list[str]]:
    occurrences: dict[str, list[dict]] = defaultdict(list)
    for blueprint in group:
        for key, module in _indexed_modules(blueprint).items():
            occurrences[key].append(module)
    count = len(group)
    required, optional, excluded, averages = [], [], [], []
    for key, items in sorted(occurrences.items()):
        frequency = len(items) / count
        if frequency < 0.30:
            excluded.append(key)
            continue
        module_type = key.rsplit("-", 1)[0]
        module = {
            "id": key,
            "type": module_type,
            "label": items[0].get("label") or module_type,
            "x": round(sum(float(item["x"]) for item in items) / len(items), 4),
            "y": round(sum(float(item["y"]) for item in items) / len(items), 4),
            "width": round(sum(float(item["width"]) for item in items) / len(items), 4),
            "height": round(sum(float(item["height"]) for item in items) / len(items), 4),
            "importance": int(items[0].get("importance", 1)),
            "priority": len(averages) + 1,
            "alignment": items[0].get("alignment", "center"),
            "description": "",
            "content_summary": "",
            "confidence": round(frequency, 4),
        }
        # Floating averages of valid normalized boxes remain valid, but clamp tiny
        # precision drift before running the canonical validator.
        module["width"] = min(module["width"], round(1 - module["x"], 4))
        module["height"] = min(module["height"], round(1 - module["y"], 4))
        averages.append(module)
        (required if frequency >= 0.80 else optional).append(key)
    validate_modules(averages, len(averages))
    return averages, required, optional, excluded


def _pattern_code(group: list[models.LayoutBlueprint], modules: list[dict]) -> str:
    anchor = group[0]
    stable = {
        "orientation": anchor.orientation,
        "canvas_ratio": anchor.canvas_ratio,
        "information_density": anchor.information_density,
        "core_modules": [
            {
                "type": module["type"],
                "position_bin": [round(module["x"], 1), round(module["y"], 1)],
            }
            for module in modules
            if module["type"] in CORE_TYPES
        ],
        "reading_flow": anchor.reading_flow,
        "grid_columns": anchor.grid_columns,
        "grid_rows": anchor.grid_rows,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    return "LP-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()


def _confidence(evidence_count: int) -> str:
    if evidence_count >= 8:
        return "high"
    if evidence_count >= 5:
        return "medium"
    return "candidate"


def aggregate_business_context(cases: list[models.Case]) -> dict[str, Any]:
    fields = {
        "product_categories": ("product_category", "product_category"),
        "channels": ("channel", "channel"),
        "campaign_stages": ("campaign_stage", "campaign_stage"),
        "business_goals": ("business_goal", "business_goal"),
    }
    result: dict[str, dict[str, int]] = {}
    for output_key, (attribute, taxonomy_field) in fields.items():
        counts = Counter(
            normalize_business_value(taxonomy_field, getattr(case, attribute, "") or "")
            for case in cases
            if (getattr(case, attribute, "") or "").strip()
        )
        result[output_key] = dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    purposes = Counter()
    for case in cases:
        value = (case.content_purpose or "").strip() or (
            case.content_type or ""
        ).strip()
        if value:
            purposes[normalize_business_value("content_purpose", value)] += 1
    result["content_purposes"] = dict(
        sorted(purposes.items(), key=lambda item: (-item[1], item[0]))
    )
    return result


def _name(modules: set[str], orientation: str) -> str:
    if "parameter_table" in modules and "product_image" in modules:
        return "上产品下参数型"
    if "person_image" in modules and "product_image" in modules:
        return "人物场景与产品组合型"
    if "feature_list" in modules or len(modules) >= 6:
        return "多模块信息卡片型"
    if "product_image" in modules and "main_title" in modules:
        return "左文右产品型" if orientation == "landscape" else "中心产品聚焦型"
    return "通用信息排版型"


def discover_candidates(
    db: Session,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    minimum_evidence: int = DEFAULT_MINIMUM_EVIDENCE,
) -> list[dict[str, Any]]:
    eligible = latest_verified_blueprints(db)
    buckets: dict[tuple[str, str, str], list[models.LayoutBlueprint]] = defaultdict(list)
    for blueprint in eligible:
        buckets[_primary_key(blueprint)].append(blueprint)

    candidates: list[dict[str, Any]] = []
    for key in sorted(buckets):
        for group in _cluster(buckets[key], similarity_threshold):
            unique_cases = {item.case_id for item in group}
            if len(unique_cases) < minimum_evidence:
                continue
            averages, required, optional, excluded = _average_modules(group)
            anchor = group[0]
            similarities = [
                {
                    "case_id": item.case_id,
                    "blueprint_id": item.id,
                    "similarity": structure_similarity(anchor, item),
                }
                for item in group
            ]
            mean_similarity = round(
                sum(item["similarity"]["total"] for item in similarities)
                / len(similarities),
                4,
            )
            case_ids = sorted(unique_cases)
            blueprint_ids = [item.id for item in sorted(group, key=lambda value: value.case_id)]
            module_types = {item["type"] for item in averages}
            evidence_cases = [
                item.case for item in group if item.case is not None
            ]
            business_context = aggregate_business_context(evidence_cases)
            historical_ids = [
                pattern.id
                for pattern in db.query(models.LayoutPattern).filter(
                    models.LayoutPattern.review_status == "verified",
                    models.LayoutPattern.orientation == anchor.orientation,
                    models.LayoutPattern.canvas_ratio == anchor.canvas_ratio,
                    models.LayoutPattern.information_density
                    == anchor.information_density,
                ).all()
                if pattern.pattern_code != _pattern_code(group, averages)
            ]
            candidates.append({
                "pattern_code": _pattern_code(group, averages),
                "name": _name(module_types, anchor.orientation),
                "description": (
                    f"由 {len(case_ids)} 个不同案例的最新已确认蓝图，"
                    f"按结构相似度阈值 {similarity_threshold:.2f} 自动发现。"
                ),
                "canvas_ratio": anchor.canvas_ratio,
                "orientation": anchor.orientation,
                "grid_columns": anchor.grid_columns,
                "grid_rows": anchor.grid_rows,
                "reading_flow": anchor.reading_flow,
                "information_density": anchor.information_density,
                "layout_signature": anchor.layout_signature,
                "average_positions_json": averages,
                "module_structure_json": averages,
                "required_modules_json": required,
                "optional_modules_json": optional,
                "suitable_scenes_json": [],
                "unsuitable_scenes_json": [],
                "product_category_tags_json": list(
                    business_context["product_categories"]
                ),
                "content_purpose_tags_json": list(
                    business_context["content_purposes"]
                ),
                "campaign_stage_tags_json": list(
                    business_context["campaign_stages"]
                ),
                "business_context_json": business_context,
                "business_context_review_status": "suggested",
                "business_context_reviewer": "",
                "evidence_case_ids_json": case_ids,
                "evidence_blueprint_ids_json": blueprint_ids,
                "evidence_count": len(case_ids),
                "confidence_level": _confidence(len(case_ids)),
                "discovery_method": DISCOVERY_METHOD,
                "review_status": "draft",
                "historical_pattern_ids": sorted(historical_ids),
                "warnings": (
                    ["存在同画布分组的历史已确认模式；本次候选不会覆盖或删除它们。"]
                    if historical_ids else []
                ),
                "mean_similarity": mean_similarity,
                "similarities": similarities,
                "grouping_basis": {
                    "orientation": key[0],
                    "canvas_ratio": key[1],
                    "information_density": key[2],
                    "threshold": similarity_threshold,
                    "weights": {
                        "module_types": 0.35,
                        "position_size": 0.35,
                        "grid_reading_flow": 0.15,
                        "canvas_density": 0.15,
                    },
                },
                "participating_modules": required + optional,
                "excluded_modules": excluded,
            })
    return candidates


def rebuild(
    db: Session,
    *,
    dry_run: bool,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    minimum_evidence: int = DEFAULT_MINIMUM_EVIDENCE,
) -> dict[str, Any]:
    candidates = discover_candidates(
        db,
        similarity_threshold=similarity_threshold,
        minimum_evidence=minimum_evidence,
    )
    written = updated = skipped = 0
    if not dry_run:
        try:
            for data in candidates:
                current = db.query(models.LayoutPattern).filter(
                    models.LayoutPattern.pattern_code == data["pattern_code"]
                ).first()
                if current and (
                    current.review_status in {"verified", "disabled"}
                    or current.discovery_method != DISCOVERY_METHOD
                ):
                    skipped += 1
                    continue
                if current is None:
                    current = models.LayoutPattern(
                        pattern_code=data["pattern_code"],
                        discovery_method=DISCOVERY_METHOD,
                    )
                    db.add(current)
                    written += 1
                else:
                    updated += 1
                persisted_fields = {
                    key: value for key, value in data.items()
                    if key not in {
                        "grouping_basis", "mean_similarity", "similarities",
                        "participating_modules", "excluded_modules",
                        "historical_pattern_ids", "warnings",
                    }
                }
                evidence_changed = set(_loads(
                    current.evidence_case_ids_json or current.source_case_ids, []
                )) != set(data["evidence_case_ids_json"])
                if (
                    current.business_context_review_status == "verified"
                    and current.id is not None
                ):
                    for protected in {
                        "product_category_tags_json",
                        "content_purpose_tags_json",
                        "campaign_stage_tags_json",
                        "business_context_json",
                        "business_context_review_status",
                        "business_context_reviewer",
                    }:
                        persisted_fields.pop(protected, None)
                for key, value in persisted_fields.items():
                    setattr(
                        current,
                        key,
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (list, dict)) else value,
                    )
                current.modules_json = json.dumps(data["average_positions_json"], ensure_ascii=False)
                current.source_case_ids = json.dumps(data["evidence_case_ids_json"])
                current.source_blueprint_ids = json.dumps(data["evidence_blueprint_ids_json"])
                current.module_count = len(data["average_positions_json"])
                current.model_name = "explainable-rule-engine"
                current.prompt_version = "layout-pattern-rules-v2"
                current.generated_at = dt.datetime.utcnow()
                if evidence_changed and current.business_context_review_status == "verified":
                    current.business_context_review_status = "stale"
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "dry_run": dry_run,
        "similarity_threshold": similarity_threshold,
        "minimum_evidence": minimum_evidence,
        "candidate_count": len(candidates),
        "written": written,
        "updated": updated,
        "skipped": skipped,
        "candidates": candidates,
    }


def evidence_report(db: Session, pattern: models.LayoutPattern) -> dict[str, Any]:
    case_ids = _loads(pattern.evidence_case_ids_json or pattern.source_case_ids, [])
    blueprint_ids = _loads(
        pattern.evidence_blueprint_ids_json or pattern.source_blueprint_ids,
        [],
    )
    cases = db.query(models.Case).filter(models.Case.id.in_(case_ids)).all() if case_ids else []
    blueprints = (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.id.in_(blueprint_ids))
        .all()
        if blueprint_ids else []
    )
    by_id = {item.id: item for item in blueprints}
    ordered = [by_id[item_id] for item_id in blueprint_ids if item_id in by_id]
    anchor = ordered[0] if ordered else None
    similarities = [
        {
            "case_id": item.case_id,
            "blueprint_id": item.id,
            "similarity": structure_similarity(anchor, item),
        }
        for item in ordered
    ] if anchor else []
    participating = _loads(pattern.required_modules_json, []) + _loads(pattern.optional_modules_json, [])
    all_keys = {
        key for blueprint in ordered for key in _indexed_modules(blueprint)
    }
    return {
        "cases": cases,
        "blueprints": ordered,
        "similarities": similarities,
        "participating_modules": participating,
        "excluded_modules": sorted(all_keys - set(participating)),
        "evidence_count": len(set(case_ids)),
    }
