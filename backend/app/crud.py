"""数据持久化与查询逻辑。"""
from __future__ import annotations

import json
import datetime as dt
import math
import re
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from . import config, llm, models
from .vision_provider import analyze_layout_regions
from .layout_blueprint import validate_modules
from .schemas import (
    AnalysisResult,
    CaseReviewInput,
    LayoutBlueprintInput,
    LayoutModule,
    BusinessRequirementCreate,
    LayoutDirectionFeedbackCreate,
    LayoutPatternCreate,
    LayoutPatternUpdate,
)


def get_or_create_tag(db: Session, name: str, category: str = "style") -> models.Tag:
    name = name.strip()
    tag = db.query(models.Tag).filter(models.Tag.name == name).first()
    if not tag:
        tag = models.Tag(name=name, category=category)
        db.add(tag)
        db.flush()
    return tag


def _image_canvas(image: models.Image | None) -> tuple[int, int]:
    if image is None:
        return (1, 1)
    path = config.UPLOAD_DIR / Path(image.url or "").name
    try:
        with PILImage.open(path) as source:
            return source.size
    except Exception:
        return (1, 1)


def _canvas_ratio(width: int, height: int) -> str:
    divisor = math.gcd(max(1, width), max(1, height))
    return f"{max(1, width) // divisor}:{max(1, height) // divisor}"


def _merge_region_bands(
    bands: list[tuple[float, float]],
    limit: int = 6,
) -> list[tuple[float, float]]:
    clean = [
        (max(0.0, start), min(1.0, end))
        for start, end in bands
        if end - start >= 0.018
    ]
    if len(clean) <= limit:
        return clean
    chunk_size = math.ceil(len(clean) / limit)
    return [
        (chunk[0][0], chunk[-1][1])
        for offset in range(0, len(clean), chunk_size)
        if (chunk := clean[offset : offset + chunk_size])
    ]


def _edge_bands_to_boxes(
    bands: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Pair projected leading/trailing edges into visible content boxes."""
    ordered = sorted(bands)
    if len(ordered) < 2:
        return ordered
    boxes = []
    for offset in range(0, len(ordered) - 1, 2):
        start = ordered[offset][0]
        end = ordered[offset + 1][1]
        if end > start:
            boxes.append((start, end))
    if len(ordered) % 2:
        start, end = ordered[-1]
        boxes.append((max(0, start - 0.01), min(1, end + 0.01)))
    return boxes


def _detected_layout_modules(
    image: models.Image,
    alignment: str,
) -> list[dict]:
    path = config.UPLOAD_DIR / Path(image.url or "").name
    regions = analyze_layout_regions(str(path))
    top, left, bottom, right = regions["bbox"]
    content_width = max(0.05, right - left)
    row_bands = _merge_region_bands(
        _edge_bands_to_boxes(regions.get("row_bands") or [])
    )
    col_bands = _merge_region_bands(
        _edge_bands_to_boxes(regions.get("col_bands") or []),
        limit=4,
    )
    if not row_bands:
        return []

    row_bands = [
        (max(top, start), min(bottom, end))
        for start, end in row_bands
        if min(bottom, end) - max(top, start) >= 0.018
    ]
    if not row_bands:
        return []
    largest_index = max(
        range(len(row_bands)),
        key=lambda index: row_bands[index][1] - row_bands[index][0],
    )
    modules: list[dict] = []
    for index, (start, end) in enumerate(row_bands):
        height = end - start
        should_split = (
            index == largest_index
            and 2 <= len(col_bands) <= 4
            and height >= 0.08
        )
        if should_split:
            for col_index, (col_start, col_end) in enumerate(col_bands, 1):
                x = max(left, col_start)
                width = min(right, col_end) - x
                if width < 0.025:
                    continue
                modules.append(
                    {
                        "id": f"module-row-{index + 1}-col-{col_index}",
                        "type": "product_image",
                        "x": round(x, 4),
                        "y": round(start, 4),
                        "width": round(width, 4),
                        "height": round(height, 4),
                        "priority": len(modules) + 1,
                        "alignment": alignment or "center",
                        "description": f"主内容分栏 {col_index}",
                    }
                )
            continue
        module_type = (
            "title"
            if index == 0
            else "cta"
            if index == len(row_bands) - 1 and height <= 0.12
            else "product_image"
            if index == largest_index
            else "supporting_text"
        )
        modules.append(
            {
                "id": f"module-row-{index + 1}",
                "type": module_type,
                "x": round(left, 4),
                "y": round(start, 4),
                "width": round(content_width, 4),
                "height": round(height, 4),
                "priority": len(modules) + 1,
                "alignment": alignment or "center",
                "description": {
                    "title": "检测到的顶部标题框",
                    "product_image": "检测到的主视觉框",
                    "supporting_text": "检测到的辅助信息框",
                    "cta": "检测到的底部引导框",
                }[module_type],
            }
        )
    return modules[:12]


def _layout_blueprint_model(
    case_id: int,
    payload: LayoutBlueprintInput,
    version: int,
) -> models.LayoutBlueprint:
    values = payload.model_dump()
    modules = values.pop("modules_json")
    margins = values.pop("margins")
    focal_region = values.pop("focal_region")
    return models.LayoutBlueprint(
        case_id=case_id,
        version=version,
        modules_json=json.dumps(modules, ensure_ascii=False),
        margins=json.dumps(margins, ensure_ascii=False),
        margins_json=json.dumps(margins, ensure_ascii=False),
        focal_region=(
            json.dumps(focal_region, ensure_ascii=False)
            if focal_region is not None
            else ""
        ),
        **values,
    )


def build_initial_layout_blueprint(
    image: models.Image,
    result: AnalysisResult,
) -> LayoutBlueprintInput:
    """Create a deterministic normalized skeleton from existing analysis."""
    width, height = _image_canvas(image)
    ratio = width / max(1, height)
    orientation = (
        "landscape" if ratio > 1.1 else "portrait" if ratio < 0.9 else "square"
    )
    templates = {
        "portrait": [
            ("title", 0.08, 0.05, 0.84, 0.12, "主标题区域"),
            ("product_image", 0.12, 0.22, 0.76, 0.44, "产品或内容主视觉"),
            ("supporting_text", 0.10, 0.70, 0.80, 0.12, "辅助信息区域"),
            ("cta", 0.30, 0.87, 0.40, 0.07, "行动引导区域"),
        ],
        "landscape": [
            ("title", 0.06, 0.08, 0.40, 0.16, "主标题区域"),
            ("supporting_text", 0.06, 0.34, 0.40, 0.24, "辅助信息区域"),
            ("product_image", 0.52, 0.12, 0.42, 0.62, "产品或内容主视觉"),
            ("cta", 0.06, 0.72, 0.28, 0.12, "行动引导区域"),
        ],
        "square": [
            ("title", 0.08, 0.06, 0.84, 0.14, "主标题区域"),
            ("product_image", 0.15, 0.24, 0.70, 0.46, "产品或内容主视觉"),
            ("supporting_text", 0.10, 0.74, 0.80, 0.10, "辅助信息区域"),
            ("cta", 0.32, 0.88, 0.36, 0.06, "行动引导区域"),
        ],
    }
    template_modules = [
        {
            "id": f"module-{index}",
            "type": module_type,
            "x": x,
            "y": y,
            "width": module_width,
            "height": module_height,
            "priority": index,
            "alignment": result.layout.alignment or "center",
            "description": description,
        }
        for index, (
            module_type,
            x,
            y,
            module_width,
            module_height,
            description,
        ) in enumerate(templates[orientation], 1)
    ]
    detected_modules: list[dict] = []
    try:
        detected_modules = _detected_layout_modules(
            image,
            result.layout.alignment,
        )
    except Exception:
        detected_modules = []
    used_ai_modules = False
    ai_modules = result.layout.blueprint_modules or []
    if ai_modules:
        try:
            normalized_ai_modules = [
                LayoutModule.model_validate(item).model_dump()
                for item in ai_modules
            ]
            validate_modules(normalized_ai_modules, len(normalized_ai_modules))
            ai_modules = normalized_ai_modules
            used_ai_modules = True
        except Exception:
            ai_modules = []
    used_detection = len(detected_modules) >= 2
    modules = (
        ai_modules
        if used_ai_modules
        else detected_modules
        if used_detection
        else template_modules
    )
    visual = max(
        (
            module
            for module in modules
            if module["type"] == "product_image"
        ),
        key=lambda module: module["width"] * module["height"],
        default=max(
            modules,
            key=lambda module: module["width"] * module["height"],
        ),
    )
    raw_grid = result.layout.grid_columns or ""
    grid_match = re.search(r"\d+", raw_grid)
    grid_columns = max(1, min(24, int(grid_match.group()))) if grid_match else 6
    text_hint = (result.typography.text_ratio or "").lower()
    text_image_ratio = (
        0.65
        if "重文字" in text_hint or "text-heavy" in text_hint
        else 0.25
        if "以图为主" in text_hint or "image-led" in text_hint
        else 0.5
    )
    information_density = (
        "high"
        if text_image_ratio >= 0.6
        else "low"
        if text_image_ratio <= 0.3
        else "medium"
    )
    source_model = (result.analyzed_by or "").strip()
    heuristic_sources = {"", "启发式规则", "heuristic"}
    source_label = (
        source_model
        if source_model not in heuristic_sources
        else "heuristic"
    )
    model_name = (
        source_label
        if used_ai_modules
        else f"region-detection-fallback+{source_label}"
        if used_detection
        else f"template-fallback+{source_label}"
    )
    prompt_version = "layout-blueprint-v2"
    return LayoutBlueprintInput(
        canvas_ratio=_canvas_ratio(width, height),
        orientation=orientation,
        grid_columns=grid_columns,
        grid_rows=12,
        margins={"top": 0.05, "right": 0.06, "bottom": 0.05, "left": 0.06},
        alignment=result.layout.alignment or "center",
        reading_flow=(
            "left-to-right" if orientation == "landscape" else "top-to-bottom"
        ),
        focal_region={
            key: visual[key] for key in ("x", "y", "width", "height")
        },
        information_density=information_density,
        text_image_ratio=text_image_ratio,
        modules_json=modules,
        review_status="ai_generated",
        model_name=model_name,
        prompt_version=prompt_version,
    )


def build_layout_blueprint_for_case(
    case: models.Case,
) -> LayoutBlueprintInput:
    analysis = analysis_to_dict(case.analysis) or {}
    result = AnalysisResult(
        basics={
            "image_type": case.content_type or "",
            "industry": case.industry or "",
            "scene": case.scene or "",
        },
        style=analysis.get("style") or {},
        color=analysis.get("color") or {},
        composition=analysis.get("composition") or {},
        light=analysis.get("light") or {},
        material=analysis.get("material") or "",
        layout=analysis.get("layout") or {},
        typography=analysis.get("typography") or {},
        design_rules=analysis.get("design_rules") or {},
        insights=analysis.get("insights"),
        prompt=analysis.get("prompt") or "",
        summary=case.summary or "",
        name=case.name or "",
        tags=[tag.name for tag in case.tags],
        analyzed_by=(
            analysis.get("model_name")
            or analysis.get("analyzed_by")
            or "heuristic"
        ),
    )
    return build_initial_layout_blueprint(case.image, result)


def _json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def create_layout_pattern(
    db: Session,
    payload: LayoutPatternCreate | LayoutPatternUpdate,
) -> models.LayoutPattern:
    """Distill reusable structure from verified layout blueprint evidence."""
    blueprints = (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.id.in_(payload.source_blueprint_ids))
        .order_by(models.LayoutBlueprint.id)
        .all()
    )
    found_ids = {item.id for item in blueprints}
    missing = [
        blueprint_id
        for blueprint_id in payload.source_blueprint_ids
        if blueprint_id not in found_ids
    ]
    if missing:
        raise ValueError(f"排版骨架不存在: {missing}")
    unverified = [
        item.id for item in blueprints if item.review_status != "verified"
    ]
    if unverified:
        raise ValueError(f"只能从已确认排版骨架沉淀模式: {unverified}")

    anchor = blueprints[0]
    source_case_ids = list(dict.fromkeys(item.case_id for item in blueprints))
    matching_patterns = (
        db.query(models.LayoutPattern)
        .filter(models.LayoutPattern.name == payload.name.strip())
        .order_by(models.LayoutPattern.version.desc())
        .all()
    )
    version = (matching_patterns[0].version + 1) if matching_patterns else 1
    review_status = getattr(payload, "review_status", "human_edited")
    pattern = models.LayoutPattern(
        name=payload.name.strip(),
        description=payload.description,
        canvas_ratio=anchor.canvas_ratio,
        orientation=anchor.orientation,
        grid_columns=anchor.grid_columns,
        grid_rows=anchor.grid_rows,
        margins=anchor.margins,
        alignment=anchor.alignment,
        reading_flow=anchor.reading_flow,
        focal_region=anchor.focal_region,
        information_density=anchor.information_density,
        text_image_ratio=anchor.text_image_ratio,
        module_count=anchor.module_count,
        modules_json=anchor.modules_json,
        source_blueprint_ids=json.dumps(
            payload.source_blueprint_ids,
            ensure_ascii=False,
        ),
        source_case_ids=json.dumps(source_case_ids, ensure_ascii=False),
        industry_tags=json.dumps(payload.industry_tags, ensure_ascii=False),
        scene_tags=json.dumps(payload.scene_tags, ensure_ascii=False),
        channel_tags=json.dumps(payload.channel_tags, ensure_ascii=False),
        business_goal_tags=json.dumps(
            payload.business_goal_tags,
            ensure_ascii=False,
        ),
        usage_notes=payload.usage_notes,
        version=version,
        review_status=review_status,
        model_name="human-distilled-layout-pattern",
        prompt_version="layout-pattern-distillation-v1",
        editor=payload.editor.strip(),
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


def list_layout_patterns(
    db: Session,
    *,
    orientation: str = "",
    scene: str = "",
    channel: str = "",
    review_status: str = "",
) -> list[models.LayoutPattern]:
    query = db.query(models.LayoutPattern)
    if orientation:
        query = query.filter(models.LayoutPattern.orientation == orientation)
    if review_status:
        query = query.filter(models.LayoutPattern.review_status == review_status)
    items = query.order_by(
        models.LayoutPattern.updated_at.desc(),
        models.LayoutPattern.id.desc(),
    ).all()
    if scene:
        items = [
            item for item in items if scene in _json_list(item.scene_tags)
        ]
    if channel:
        items = [
            item for item in items if channel in _json_list(item.channel_tags)
        ]
    return items


def serialize_layout_pattern(pattern: models.LayoutPattern) -> dict:
    focal_region = None
    if pattern.focal_region:
        try:
            focal_region = json.loads(pattern.focal_region)
        except (TypeError, ValueError, json.JSONDecodeError):
            focal_region = None
    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "canvas_ratio": pattern.canvas_ratio,
        "orientation": pattern.orientation,
        "grid_columns": pattern.grid_columns,
        "grid_rows": pattern.grid_rows,
        "margins": json.loads(pattern.margins or "{}"),
        "alignment": pattern.alignment,
        "reading_flow": pattern.reading_flow,
        "focal_region": focal_region,
        "information_density": pattern.information_density,
        "text_image_ratio": pattern.text_image_ratio,
        "module_count": pattern.module_count,
        "modules_json": _json_list(pattern.modules_json),
        "source_blueprint_ids": _json_list(pattern.source_blueprint_ids),
        "source_case_ids": _json_list(pattern.source_case_ids),
        "industry_tags": _json_list(pattern.industry_tags),
        "scene_tags": _json_list(pattern.scene_tags),
        "channel_tags": _json_list(pattern.channel_tags),
        "business_goal_tags": _json_list(pattern.business_goal_tags),
        "usage_notes": pattern.usage_notes,
        "version": pattern.version,
        "review_status": pattern.review_status,
        "model_name": pattern.model_name,
        "prompt_version": pattern.prompt_version,
        "editor": pattern.editor,
        "created_at": pattern.created_at,
        "updated_at": pattern.updated_at,
    }


def create_business_requirement(
    db: Session,
    payload: BusinessRequirementCreate,
) -> models.BusinessRequirement:
    values = payload.model_dump()
    mandatory_elements = values.pop("mandatory_elements")
    list_fields = {
        key: values.pop(key)
        for key in (
            "required_modules_json",
            "optional_modules_json",
            "forbidden_modules_json",
            "selling_points_json",
            "style_keywords_json",
        )
    }
    reference_case_ids = list(
        dict.fromkeys(
            values.pop("reference_case_ids_json")
            or values.pop("reference_case_ids")
        )
    )
    values.pop("reference_case_ids", None)
    if reference_case_ids:
        existing_case_ids = {
            case_id
            for (case_id,) in db.query(models.Case.id)
            .filter(models.Case.id.in_(reference_case_ids))
            .all()
        }
        missing = [
            case_id
            for case_id in reference_case_ids
            if case_id not in existing_case_ids
        ]
        if missing:
            raise ValueError(f"参考案例不存在: {missing}")
    requirement = models.BusinessRequirement(
        **values,
        mandatory_elements=json.dumps(mandatory_elements, ensure_ascii=False),
        reference_case_ids=json.dumps(reference_case_ids, ensure_ascii=False),
        reference_case_ids_json=json.dumps(reference_case_ids, ensure_ascii=False),
        **{
            key: json.dumps(value, ensure_ascii=False)
            for key, value in list_fields.items()
        },
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def serialize_business_requirement(
    requirement: models.BusinessRequirement,
) -> dict:
    return {
        "id": requirement.id,
        "title": requirement.title,
        "request_text": requirement.request_text,
        "industry": requirement.industry,
        "product_category": requirement.product_category,
        "channel": requirement.channel,
        "canvas_ratio": requirement.canvas_ratio,
        "orientation": requirement.orientation,
        "campaign_stage": requirement.campaign_stage,
        "business_goal": requirement.business_goal,
        "target_audience": requirement.target_audience,
        "content_purpose": requirement.content_purpose or "",
        "required_modules_json": _json_list(requirement.required_modules_json),
        "optional_modules_json": _json_list(requirement.optional_modules_json),
        "forbidden_modules_json": _json_list(requirement.forbidden_modules_json),
        "selling_points_json": _json_list(requirement.selling_points_json),
        "style_keywords_json": _json_list(requirement.style_keywords_json),
        "raw_requirement": requirement.raw_requirement or requirement.request_text,
        "reference_case_ids_json": _json_list(
            requirement.reference_case_ids_json or requirement.reference_case_ids
        ),
        "reference_image_path": requirement.reference_image_path or "",
        "creator": requirement.creator or requirement.created_by,
        "key_message": requirement.key_message,
        "mandatory_elements": _json_list(requirement.mandatory_elements),
        "information_density": requirement.information_density,
        "reference_case_ids": _json_list(requirement.reference_case_ids),
        "created_by": requirement.created_by,
        "status": requirement.status,
        "created_at": requirement.created_at,
        "updated_at": requirement.updated_at,
    }


def update_business_requirement(
    db: Session,
    requirement: models.BusinessRequirement,
    payload: BusinessRequirementCreate,
) -> models.BusinessRequirement:
    if requirement.status == "archived":
        raise ValueError("已归档需求不能修改")
    values = payload.model_dump()
    reference_ids = list(
        dict.fromkeys(
            values.pop("reference_case_ids_json")
            or values.pop("reference_case_ids")
        )
    )
    values.pop("reference_case_ids", None)
    if reference_ids:
        existing = {
            row[0]
            for row in db.query(models.Case.id)
            .filter(models.Case.id.in_(reference_ids))
            .all()
        }
        missing = [case_id for case_id in reference_ids if case_id not in existing]
        if missing:
            raise ValueError(f"参考案例不存在: {missing}")
    for key in (
        "required_modules_json",
        "optional_modules_json",
        "forbidden_modules_json",
        "selling_points_json",
        "style_keywords_json",
    ):
        setattr(requirement, key, json.dumps(values.pop(key), ensure_ascii=False))
    requirement.reference_case_ids = json.dumps(reference_ids, ensure_ascii=False)
    requirement.reference_case_ids_json = json.dumps(reference_ids, ensure_ascii=False)
    requirement.mandatory_elements = json.dumps(
        values.pop("mandatory_elements"), ensure_ascii=False
    )
    for key, value in values.items():
        setattr(requirement, key, value)
    db.commit()
    db.refresh(requirement)
    return requirement


def _text_overlap(left: str, right: str) -> float:
    tokens_left = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (left or "").lower()))
    tokens_right = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (right or "").lower()))
    if not tokens_left or not tokens_right:
        return 0
    return len(tokens_left & tokens_right) / max(1, len(tokens_left))


def match_business_requirement(
    db: Session,
    requirement: models.BusinessRequirement,
    *,
    pattern_limit: int = 6,
    case_limit: int = 12,
) -> dict:
    """Explainable structured retrieval without company preference weighting."""
    patterns = (
        db.query(models.LayoutPattern)
        .filter(models.LayoutPattern.review_status == "verified")
        .all()
    )
    pattern_matches: list[dict] = []
    related_case_ids: set[int] = set()
    requirement_text = " ".join(
        [
            requirement.request_text,
            requirement.business_goal,
            requirement.key_message,
            requirement.campaign_stage,
        ]
    )
    for pattern in patterns:
        score = 20.0
        reasons = ["人工确认排版模式"]
        if requirement.orientation and pattern.orientation == requirement.orientation:
            score += 18
            reasons.append("画布方向一致")
        if requirement.canvas_ratio and pattern.canvas_ratio == requirement.canvas_ratio:
            score += 12
            reasons.append("画布比例一致")
        if (
            requirement.information_density
            and pattern.information_density == requirement.information_density
        ):
            score += 10
            reasons.append("信息密度一致")
        tag_checks = [
            (requirement.industry, _json_list(pattern.industry_tags), "行业"),
            (requirement.channel, _json_list(pattern.channel_tags), "渠道"),
            (
                requirement.campaign_stage,
                _json_list(pattern.scene_tags),
                "业务场景",
            ),
            (
                requirement.business_goal,
                _json_list(pattern.business_goal_tags),
                "业务目标",
            ),
        ]
        for expected, tags, label in tag_checks:
            if expected and any(
                expected in tag or tag in expected for tag in tags if tag
            ):
                score += 14
                reasons.append(f"{label}匹配")
        overlap = _text_overlap(
            requirement_text,
            f"{pattern.description} {pattern.usage_notes}",
        )
        if overlap:
            score += round(overlap * 20, 2)
            reasons.append("需求语义与适用说明相关")
        sources = _json_list(pattern.source_case_ids)
        related_case_ids.update(int(case_id) for case_id in sources)
        pattern_matches.append(
            {
                "pattern": serialize_layout_pattern(pattern),
                "score": round(score, 2),
                "reasons": reasons,
            }
        )
    pattern_matches.sort(
        key=lambda item: (-item["score"], item["pattern"]["id"])
    )
    pattern_matches = pattern_matches[:pattern_limit]

    latest_verified: dict[int, models.LayoutBlueprint] = {}
    for blueprint in (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.review_status == "verified")
        .order_by(
            models.LayoutBlueprint.case_id,
            models.LayoutBlueprint.version.desc(),
        )
        .all()
    ):
        latest_verified.setdefault(blueprint.case_id, blueprint)
    cases = (
        db.query(models.Case)
        .filter(models.Case.id.in_(list(latest_verified)))
        .all()
        if latest_verified
        else []
    )
    case_matches: list[dict] = []
    reference_case_ids = set(_json_list(requirement.reference_case_ids))
    for case in cases:
        blueprint = latest_verified[case.id]
        score = 10.0
        reasons = ["案例具有人工确认排版骨架"]
        if case.id in related_case_ids:
            score += 20
            reasons.append("入选排版模式的来源案例")
        if case.id in reference_case_ids:
            score += 25
            reasons.append("需求指定参考案例")
        for actual, expected, label in [
            (case.industry, requirement.industry, "行业"),
            (case.product_category, requirement.product_category, "产品品类"),
            (case.channel, requirement.channel, "渠道"),
            (case.campaign_stage, requirement.campaign_stage, "业务场景"),
        ]:
            if expected and actual and (expected in actual or actual in expected):
                score += 12
                reasons.append(f"{label}匹配")
        if requirement.orientation and blueprint.orientation == requirement.orientation:
            score += 12
            reasons.append("骨架方向一致")
        overlap = _text_overlap(
            requirement_text,
            f"{case.summary} {case.business_goal}",
        )
        if overlap:
            score += round(overlap * 15, 2)
            reasons.append("案例内容与需求相关")
        case_matches.append(
            {
                "case_id": case.id,
                "name": case.name,
                "blueprint_id": blueprint.id,
                "score": round(score, 2),
                "reasons": reasons,
            }
        )
    case_matches.sort(key=lambda item: (-item["score"], item["case_id"]))
    return {
        "requirement": serialize_business_requirement(requirement),
        "pattern_matches": pattern_matches,
        "case_matches": case_matches[:case_limit],
    }


def _safe_region(module: dict) -> dict:
    module["x"] = round(max(0, min(0.98, float(module.get("x", 0)))), 4)
    module["y"] = round(max(0, min(0.98, float(module.get("y", 0)))), 4)
    module["width"] = round(
        max(0.02, min(1 - module["x"], float(module.get("width", 0.1)))),
        4,
    )
    module["height"] = round(
        max(0.02, min(1 - module["y"], float(module.get("height", 0.1)))),
        4,
    )
    return module


def _direction_modules(base_modules: list[dict], strategy: str) -> list[dict]:
    modules = json.loads(json.dumps(base_modules, ensure_ascii=False))
    if strategy == "conservative":
        return modules
    if strategy == "balanced":
        for module in modules:
            if module.get("type") == "product_image":
                module["x"] = max(0.04, module["x"] - 0.03)
                module["width"] = min(
                    0.92,
                    module["width"] + 0.06,
                    1 - module["x"],
                )
                module["description"] = "强化后的产品主视觉"
            elif module.get("type") == "supporting_text":
                module["height"] = min(
                    module["height"] + 0.04,
                    1 - module["y"],
                )
        return [_safe_region(module) for module in modules]

    supporting_index = next(
        (
            index
            for index, module in enumerate(modules)
            if module.get("type") == "supporting_text"
        ),
        None,
    )
    if supporting_index is not None:
        original = modules[supporting_index]
        gap = 0.025
        half = max(0.02, (original["width"] - gap) / 2)
        left = {
            **original,
            "id": f"{original['id']}-a",
            "width": half,
            "description": "分区信息 A",
        }
        right = {
            **original,
            "id": f"{original['id']}-b",
            "x": original["x"] + half + gap,
            "width": half,
            "description": "分区信息 B",
        }
        modules[supporting_index : supporting_index + 1] = [left, right]
    for index, module in enumerate(modules, 1):
        module["priority"] = index
    return [_safe_region(module) for module in modules]


def serialize_layout_direction(direction: models.LayoutDirection) -> dict:
    focal_region = None
    if direction.focal_region:
        try:
            focal_region = json.loads(direction.focal_region)
        except (TypeError, ValueError, json.JSONDecodeError):
            focal_region = None
    return {
        "id": direction.id,
        "requirement_id": direction.requirement_id,
        "generation_version": direction.generation_version,
        "strategy_level": direction.strategy_level,
        "name": direction.name,
        "rationale": direction.rationale,
        "applicable_reason": direction.applicable_reason,
        "canvas_ratio": direction.canvas_ratio,
        "orientation": direction.orientation,
        "grid_columns": direction.grid_columns,
        "grid_rows": direction.grid_rows,
        "margins": json.loads(direction.margins or "{}"),
        "alignment": direction.alignment,
        "reading_flow": direction.reading_flow,
        "focal_region": focal_region,
        "information_density": direction.information_density,
        "text_image_ratio": direction.text_image_ratio,
        "module_count": direction.module_count,
        "modules_json": _json_list(direction.modules_json),
        "source_pattern_ids": _json_list(direction.source_pattern_ids),
        "source_case_ids": _json_list(direction.source_case_ids),
        "model_name": direction.model_name,
        "prompt_version": direction.prompt_version,
        "generation_mode": direction.generation_mode,
        "failure_reason": direction.failure_reason,
        "status": direction.status,
        "created_at": direction.created_at,
        "updated_at": direction.updated_at,
    }


def generate_layout_directions(
    db: Session,
    requirement: models.BusinessRequirement,
) -> dict:
    """Generate exactly three evidence-backed skeleton directions."""
    matched = match_business_requirement(db, requirement)
    pattern_matches = matched["pattern_matches"]
    if not pattern_matches:
        raise ValueError("没有可用的人工确认排版模式，请先沉淀并确认模式")
    case_matches = matched["case_matches"]
    source_case_ids = [
        item["case_id"] for item in case_matches[:6]
    ]
    base_pattern = pattern_matches[0]["pattern"]
    generation_version = (
        db.query(models.LayoutDirection.generation_version)
        .filter(models.LayoutDirection.requirement_id == requirement.id)
        .order_by(models.LayoutDirection.generation_version.desc())
        .limit(1)
        .scalar()
        or 0
    ) + 1
    strategies = [
        (
            "conservative",
            "方向一｜稳健沿用",
            "最大程度沿用最高匹配的已确认模式，降低设计沟通和落地风险。",
            "适合时间紧、信息确定且需要快速形成一致认知的任务。",
        ),
        (
            "balanced",
            "方向二｜主视觉强化",
            "保留信息层级，同时扩大产品主视觉并增强关键内容承载空间。",
            "适合既要清楚讲信息，又要提高第一眼产品识别的任务。",
        ),
        (
            "exploratory",
            "方向三｜信息分区探索",
            "将辅助信息拆成可比较的分区模块，形成更明确的浏览节奏。",
            "适合卖点较多、需要对比或分步骤说明的任务。",
        ),
    ]
    model_name = "heuristic-layout-direction"
    generation_mode = "heuristic"
    failure_reason = ""
    narrative_overrides: dict[str, dict] = {}
    if config.llm_enabled():
        try:
            response = llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是业务排版策略助手。只优化三个低保真排版方向的名称、"
                            "排版理由和适用原因，不生成完整设计，不改变来源证据。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "requirement": serialize_business_requirement(
                                    requirement
                                ),
                                "matched_patterns": [
                                    {
                                        "id": item["pattern"]["id"],
                                        "name": item["pattern"]["name"],
                                        "reasons": item["reasons"],
                                    }
                                    for item in pattern_matches[:3]
                                ],
                                "required_output": {
                                    "directions": [
                                        {
                                            "strategy_level": (
                                                "conservative|balanced|exploratory"
                                            ),
                                            "name": "string",
                                            "rationale": "string",
                                            "applicable_reason": "string",
                                        }
                                    ]
                                },
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=900,
                timeout=90,
            )
            for item in response.get("directions", []):
                level = item.get("strategy_level")
                if level in {"conservative", "balanced", "exploratory"}:
                    narrative_overrides[level] = item
            model_name = config.LLM_MODEL
            generation_mode = "model"
        except Exception as exc:
            failure_reason = f"{type(exc).__name__}: {str(exc)[:300]}"
    else:
        failure_reason = "文本模型未配置，使用可解释启发式方向"

    created: list[models.LayoutDirection] = []
    for index, (level, name, rationale, applicable_reason) in enumerate(
        strategies
    ):
        selected_pattern = pattern_matches[
            min(index, len(pattern_matches) - 1)
        ]["pattern"]
        override = narrative_overrides.get(level, {})
        modules = _direction_modules(
            selected_pattern["modules_json"],
            level,
        )
        source_pattern_ids = list(
            dict.fromkeys(
                [
                    base_pattern["id"],
                    selected_pattern["id"],
                ]
            )
        )
        pattern_case_ids = selected_pattern["source_case_ids"]
        direction_case_ids = list(
            dict.fromkeys(pattern_case_ids + source_case_ids)
        )
        direction = models.LayoutDirection(
            requirement_id=requirement.id,
            generation_version=generation_version,
            strategy_level=level,
            name=str(override.get("name") or name),
            rationale=str(override.get("rationale") or rationale),
            applicable_reason=str(
                override.get("applicable_reason") or applicable_reason
            ),
            canvas_ratio=(
                requirement.canvas_ratio
                or selected_pattern["canvas_ratio"]
            ),
            orientation=(
                requirement.orientation
                or selected_pattern["orientation"]
            ),
            grid_columns=selected_pattern["grid_columns"],
            grid_rows=selected_pattern["grid_rows"],
            margins=json.dumps(
                selected_pattern["margins"],
                ensure_ascii=False,
            ),
            alignment=selected_pattern["alignment"],
            reading_flow=selected_pattern["reading_flow"],
            focal_region=json.dumps(
                selected_pattern["focal_region"],
                ensure_ascii=False,
            )
            if selected_pattern["focal_region"]
            else "",
            information_density=(
                requirement.information_density
                or selected_pattern["information_density"]
            ),
            text_image_ratio=selected_pattern["text_image_ratio"],
            module_count=len(modules),
            modules_json=json.dumps(modules, ensure_ascii=False),
            source_pattern_ids=json.dumps(
                source_pattern_ids,
                ensure_ascii=False,
            ),
            source_case_ids=json.dumps(
                direction_case_ids,
                ensure_ascii=False,
            ),
            model_name=model_name,
            prompt_version="layout-direction-evidence-v1",
            generation_mode=generation_mode,
            failure_reason=failure_reason,
        )
        db.add(direction)
        created.append(direction)
    db.commit()
    for direction in created:
        db.refresh(direction)
    return {
        "requirement": serialize_business_requirement(requirement),
        "generation_version": generation_version,
        "directions": [
            serialize_layout_direction(direction) for direction in created
        ],
    }


def create_layout_direction_feedback(
    db: Session,
    direction: models.LayoutDirection,
    payload: LayoutDirectionFeedbackCreate,
) -> models.LayoutDirectionFeedback:
    adjusted_modules = (
        [module.model_dump() for module in payload.adjusted_modules_json]
        if payload.adjusted_modules_json
        else None
    )
    feedback = models.LayoutDirectionFeedback(
        requirement_id=direction.requirement_id,
        direction_id=direction.id,
        action=payload.action,
        actor=payload.actor.strip(),
        notes=payload.notes,
        adjusted_modules_json=(
            json.dumps(adjusted_modules, ensure_ascii=False)
            if adjusted_modules
            else ""
        ),
    )
    direction.status = {
        "selected": "selected",
        "adjustment_requested": "adjustment_requested",
        "adjusted_confirmed": "adjusted_confirmed",
        "rejected": "rejected",
    }[payload.action]
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def serialize_layout_direction_feedback(
    feedback: models.LayoutDirectionFeedback,
) -> dict:
    return {
        "id": feedback.id,
        "requirement_id": feedback.requirement_id,
        "direction_id": feedback.direction_id,
        "action": feedback.action,
        "actor": feedback.actor,
        "notes": feedback.notes,
        "adjusted_modules_json": (
            _json_list(feedback.adjusted_modules_json)
            if feedback.adjusted_modules_json
            else None
        ),
        "created_at": feedback.created_at,
    }


def create_case_from_analysis(
    db: Session,
    image: models.Image,
    result: AnalysisResult,
    product_category: str = "",
    asset_category: str = "layout",
    asset_subcategory: str = "",
) -> models.Case:
    """将一次 AI 拆解结果落库为完整案例卡。"""
    case = models.Case(
        image_id=image.id,
        name=result.name,
        content_type=result.basics.image_type,
        product_category=product_category,
        asset_category=asset_category,
        asset_subcategory=asset_subcategory,
        industry=result.basics.industry,
        scene=result.basics.scene,
        summary=result.summary,
        trust_status="ai_unverified",
        status="public",
    )
    db.add(case)
    db.flush()

    analysis = models.Analysis(
        case_id=case.id,
        color=result.color.model_dump_json(),
        composition=result.composition.model_dump_json(),
        light=result.light.model_dump_json(),
        material=result.material,
        layout=result.layout.model_dump_json(),
        typography=result.typography.model_dump_json(),
        style=result.style.model_dump_json(),
        design_rules=result.design_rules.model_dump_json(),
        insights=result.insights.model_dump_json() if result.insights else "",
        analyzed_by=result.analyzed_by,
        prompt=result.prompt,
        version=1,
        confidence=85 if result.analyzed_by != "启发式规则" else 55,
        model_name=result.analyzed_by,
        prompt_version="visual-analysis-v1",
        review_status="ai_unverified",
    )
    db.add(analysis)

    categorized_tags = [
        (result.layout.layout_type, "layout"),
        (result.layout.alignment, "alignment"),
        (result.typography.text_ratio, "content_ratio"),
        (result.typography.font_tone.split("（")[0].split("/")[0].strip(), "typography"),
        (result.composition.type, "composition"),
        *[(name, "style") for name in result.style.style_tags],
        *[(name, "mood") for name in result.style.mood_keywords],
        (result.basics.industry, "industry"),
        (result.basics.scene, "scene"),
        (result.basics.image_type, "content_type"),
        (result.light.type, "light"),
    ]
    for name, category in categorized_tags:
        if not name:
            continue
        tag = get_or_create_tag(db, name, category)
        if tag not in case.tags:
            case.tags.append(tag)

    snapshot = {
        "basics": result.basics.model_dump(),
        "style": result.style.model_dump(),
        "color": result.color.model_dump(),
        "composition": result.composition.model_dump(),
        "light": result.light.model_dump(),
        "material": result.material,
        "layout": result.layout.model_dump(),
        "typography": result.typography.model_dump(),
        "design_rules": result.design_rules.model_dump(),
        "insights": result.insights.model_dump() if result.insights else None,
        "prompt": result.prompt,
        "summary": result.summary,
        "name": result.name,
        "tags": result.tags,
        "analyzed_by": result.analyzed_by,
    }
    db.add(
        models.AnalysisVersion(
            case_id=case.id,
            version=1,
            payload=json.dumps(snapshot, ensure_ascii=False),
            source="ai",
            model_name=result.analyzed_by,
            prompt_version="visual-analysis-v1",
        )
    )
    db.add(
        _layout_blueprint_model(
            case.id,
            build_initial_layout_blueprint(image, result),
            version=1,
        )
    )

    db.commit()
    db.refresh(case)
    return case


def analysis_to_dict(analysis: models.Analysis | None) -> dict | None:
    if not analysis:
        return None
    return {
        "color": json.loads(analysis.color or "{}"),
        "composition": json.loads(analysis.composition or "{}"),
        "light": json.loads(analysis.light or "{}"),
        "layout": json.loads(analysis.layout or "{}"),
        "typography": json.loads(analysis.typography or "{}"),
        "style": json.loads(analysis.style or "{}"),
        "design_rules": json.loads(analysis.design_rules or "{}"),
        "insights": json.loads(analysis.insights) if (analysis.insights or "") else None,
        "analyzed_by": getattr(analysis, "analyzed_by", "") or "启发式规则",
        "version": getattr(analysis, "version", 1) or 1,
        "confidence": getattr(analysis, "confidence", 0) or 0,
        "model_name": getattr(analysis, "model_name", "") or "",
        "prompt_version": getattr(analysis, "prompt_version", "") or "",
        "review_status": getattr(analysis, "review_status", "") or "ai_unverified",
        "material": getattr(analysis, "material", ""),
        "prompt": analysis.prompt or "",
    }


def serialize_case(case: models.Case) -> dict:
    return {
        "id": case.id,
        "project_id": getattr(case, "project_id", None),
        "name": case.name,
        "content_type": getattr(case, "content_type", "") or "",
        "product_category": getattr(case, "product_category", "") or "",
        "asset_category": getattr(case, "asset_category", "") or "layout",
        "asset_subcategory": getattr(case, "asset_subcategory", "") or "",
        "industry": case.industry,
        "scene": case.scene,
        "summary": case.summary,
        "business_line": getattr(case, "business_line", "") or "",
        "channel": getattr(case, "channel", "") or "",
        "campaign_stage": getattr(case, "campaign_stage", "") or "",
        "business_goal": getattr(case, "business_goal", "") or "",
        "review_decision": getattr(case, "review_decision", "") or "",
        "review_notes": getattr(case, "review_notes", "") or "",
        "reviewer": getattr(case, "reviewer", "") or "",
        "reviewed_at": getattr(case, "reviewed_at", None),
        "trust_status": getattr(case, "trust_status", "") or "ai_unverified",
        "status": getattr(case, "status", "") or "public",
        "created_at": case.created_at,
        "image": case.image,
        "tags": case.tags,
        "analysis": analysis_to_dict(case.analysis),
    }


def serialize_layout_blueprint(blueprint: models.LayoutBlueprint) -> dict:
    return {
        "id": blueprint.id,
        "case_id": blueprint.case_id,
        "canvas_ratio": blueprint.canvas_ratio,
        "orientation": blueprint.orientation,
        "grid_columns": blueprint.grid_columns,
        "grid_rows": blueprint.grid_rows,
        "margins": json.loads(blueprint.margins or "{}"),
        "margins_json": json.loads(
            blueprint.margins_json or blueprint.margins or "{}"
        ),
        "alignment": blueprint.alignment or "",
        "reading_flow": blueprint.reading_flow or "",
        "focal_region": (
            json.loads(blueprint.focal_region)
            if (blueprint.focal_region or "").strip()
            else None
        ),
        "information_density": blueprint.information_density or "",
        "text_image_ratio": blueprint.text_image_ratio,
        "module_count": blueprint.module_count,
        "modules_json": json.loads(blueprint.modules_json or "[]"),
        "layout_signature": blueprint.layout_signature or "",
        "version": blueprint.version,
        "review_status": blueprint.review_status,
        "model_name": blueprint.model_name or "",
        "prompt_version": blueprint.prompt_version or "",
        "editor": blueprint.editor or "",
        "created_at": blueprint.created_at,
        "updated_at": blueprint.updated_at,
    }


def get_layout_blueprint(
    db: Session,
    blueprint_id: int,
) -> models.LayoutBlueprint | None:
    return db.get(models.LayoutBlueprint, blueprint_id)


def list_layout_blueprints(
    db: Session,
    case_id: int,
) -> list[models.LayoutBlueprint]:
    return (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.case_id == case_id)
        .order_by(models.LayoutBlueprint.version.desc())
        .all()
    )


def get_latest_layout_blueprint(
    db: Session,
    case_id: int,
) -> models.LayoutBlueprint | None:
    return (
        db.query(models.LayoutBlueprint)
        .filter(models.LayoutBlueprint.case_id == case_id)
        .order_by(models.LayoutBlueprint.version.desc())
        .first()
    )


def create_layout_blueprint(
    db: Session,
    case_id: int,
    payload: LayoutBlueprintInput,
    *,
    version: int | None = None,
) -> models.LayoutBlueprint:
    if not db.get(models.Case, case_id):
        raise ValueError(f"case {case_id} does not exist")
    if version is None:
        latest = get_latest_layout_blueprint(db, case_id)
        version = (latest.version + 1) if latest else 1
    blueprint = _layout_blueprint_model(case_id, payload, version)
    db.add(blueprint)
    db.commit()
    db.refresh(blueprint)
    return blueprint


def revise_layout_blueprint(
    db: Session,
    blueprint_id: int,
    payload: LayoutBlueprintInput,
) -> models.LayoutBlueprint:
    current = get_layout_blueprint(db, blueprint_id)
    if not current:
        raise ValueError(f"layout blueprint {blueprint_id} does not exist")
    return create_layout_blueprint(
        db,
        current.case_id,
        payload,
    )


def load_image_hashes(
    db: Session, asset_category: str | None = None
) -> list[tuple[str, int]]:
    """返回 (phash, case_id) 列表，用于去重比对。"""
    query = (
        db.query(models.Image.phash, models.Case.id)
        .join(models.Case, models.Case.image_id == models.Image.id)
        .filter(models.Image.phash != "")
    )
    if asset_category:
        query = query.filter(models.Case.asset_category == asset_category)
    rows = query.all()
    return [(h, cid) for h, cid in rows if h]


def find_duplicate_case_id(
    db: Session,
    phash: str,
    threshold: int = 5,
    asset_category: str | None = None,
) -> int | None:
    """在已有案例中查找与 phash 近重复的案例 id。"""
    from .imagehash import hamming

    if not phash:
        return None
    for h, cid in load_image_hashes(db, asset_category=asset_category):
        if hamming(phash, h) <= threshold:
            return cid
    return None


def search_cases(
    db: Session,
    q: str | None = None,
    tag: str | None = None,
    asset_category: str | None = None,
    asset_subcategory: str | None = None,
    project_id: int | None = None,
    trust_status: str | None = None,
    analysis_mode: str | None = None,
) -> list[models.Case]:
    query = db.query(models.Case)
    if project_id is not None:
        query = query.filter(models.Case.project_id == project_id)
    if trust_status:
        query = query.filter(models.Case.trust_status == trust_status)
    if analysis_mode == "model":
        query = query.join(models.Case.analysis).filter(
            models.Analysis.model_name != "",
            models.Analysis.model_name != "启发式规则",
        )
    elif analysis_mode == "local":
        query = query.join(models.Case.analysis).filter(
            (models.Analysis.model_name == "")
            | (models.Analysis.model_name == "启发式规则")
        )
    if asset_category:
        query = query.filter(models.Case.asset_category == asset_category)
    if asset_subcategory:
        query = query.filter(models.Case.asset_subcategory == asset_subcategory)
    if tag:
        query = query.join(models.Case.tags).filter(models.Tag.name == tag)
    cases = query.order_by(models.Case.created_at.desc()).all()
    if q:
        ql = q.lower()
        cases = [
            c
            for c in cases
            if ql in (c.name or "").lower()
            or ql in (c.summary or "").lower()
            or ql in (c.industry or "").lower()
            or any(ql in t.name.lower() for t in c.tags)
        ]
    return cases


def review_case(
    db: Session, case: models.Case, review: CaseReviewInput
) -> models.Case:
    """Apply a human correction and preserve a full version snapshot."""
    if not case.analysis:
        raise ValueError("案例没有可校验的分析结果")

    analysis = case.analysis
    layout = json.loads(analysis.layout or "{}")
    style = json.loads(analysis.style or "{}")
    color = json.loads(analysis.color or "{}")
    design_rules = json.loads(analysis.design_rules or "{}")

    if review.name is not None:
        case.name = review.name.strip() or case.name
    if review.summary is not None:
        case.summary = review.summary.strip()
    if review.layout_type is not None:
        layout["layout_type"] = review.layout_type.strip()
    if review.alignment is not None:
        layout["alignment"] = review.alignment.strip()
    if review.hierarchy is not None:
        layout["hierarchy"] = [item.strip() for item in review.hierarchy if item.strip()]
    if review.style_tags is not None:
        style["style_tags"] = [item.strip() for item in review.style_tags if item.strip()]
    if review.mood_keywords is not None:
        style["mood_keywords"] = [
            item.strip() for item in review.mood_keywords if item.strip()
        ]
    if review.color_description is not None:
        color["description"] = review.color_description.strip()
    if review.why_good is not None:
        design_rules["why_good"] = [
            item.strip() for item in review.why_good if item.strip()
        ]
    if review.reusable_methods is not None:
        design_rules["reusable_methods"] = [
            item.strip() for item in review.reusable_methods if item.strip()
        ]
    if review.prompt is not None:
        analysis.prompt = review.prompt.strip()

    analysis.layout = json.dumps(layout, ensure_ascii=False)
    analysis.style = json.dumps(style, ensure_ascii=False)
    analysis.color = json.dumps(color, ensure_ascii=False)
    analysis.design_rules = json.dumps(design_rules, ensure_ascii=False)
    analysis.version = (analysis.version or 1) + 1
    analysis.review_status = review.trust_status

    case.trust_status = review.trust_status
    case.review_decision = review.review_decision
    case.review_notes = review.review_notes.strip()
    case.reviewer = review.reviewer.strip()
    case.reviewed_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    case.business_line = review.business_line.strip()
    case.channel = review.channel.strip()
    case.campaign_stage = review.campaign_stage.strip()
    case.business_goal = review.business_goal.strip()
    if review.asset_category is not None:
        case.asset_category = review.asset_category
    keep_reasons = [item.strip() for item in review.keep_reasons if item.strip()]
    avoid_reasons = [item.strip() for item in review.avoid_reasons if item.strip()]

    payload = {
        "case": {
            "name": case.name,
            "summary": case.summary,
            "business_line": case.business_line,
            "channel": case.channel,
            "campaign_stage": case.campaign_stage,
            "business_goal": case.business_goal,
            "asset_category": case.asset_category,
            "review_decision": case.review_decision,
            "review_notes": case.review_notes,
            "trust_status": case.trust_status,
            "keep_reasons": keep_reasons,
            "avoid_reasons": avoid_reasons,
        },
        "analysis": analysis_to_dict(analysis),
    }
    db.add(
        models.AnalysisVersion(
            case_id=case.id,
            version=analysis.version,
            payload=json.dumps(payload, ensure_ascii=False),
            source="manual",
            model_name=analysis.model_name or analysis.analyzed_by,
            prompt_version=analysis.prompt_version,
            editor=case.reviewer,
        )
    )
    action = (
        "recommend"
        if review.trust_status == "company_recommended"
        else "reject"
        if review.trust_status == "rejected"
        else "confirm"
        if review.trust_status == "verified"
        else "edit"
    )
    db.add(
        models.CaseReview(
            case_id=case.id,
            project_id=case.project_id,
            reviewer=case.reviewer,
            action=action,
            trust_status=case.trust_status,
            decision=case.review_decision,
            notes=case.review_notes,
            keep_reasons=json.dumps(keep_reasons, ensure_ascii=False),
            avoid_reasons=json.dumps(avoid_reasons, ensure_ascii=False),
            corrected_payload=json.dumps(payload, ensure_ascii=False),
            analysis_version=analysis.version,
        )
    )
    if review.review_decision in {"adopt", "reject"}:
        db.add(
            models.PreferenceEvent(
                case_id=case.id,
                project_id=case.project_id,
                event_type=review.review_decision,
                value=1,
                actor=case.reviewer,
                context=case.review_notes,
            )
        )
    db.commit()
    db.refresh(case)
    return case


def replace_analysis_from_result(
    db: Session,
    case: models.Case,
    result: AnalysisResult,
    source: str = "regenerate",
) -> models.Case:
    """Replace the current AI analysis while preserving the previous versions."""
    analysis = case.analysis
    if not analysis:
        raise ValueError("案例没有分析记录")
    case.name = result.name
    case.content_type = result.basics.image_type
    case.industry = result.basics.industry
    case.scene = result.basics.scene
    case.summary = result.summary
    case.trust_status = "ai_unverified"
    analysis.color = result.color.model_dump_json()
    analysis.composition = result.composition.model_dump_json()
    analysis.light = result.light.model_dump_json()
    analysis.material = result.material
    analysis.layout = result.layout.model_dump_json()
    analysis.typography = result.typography.model_dump_json()
    analysis.style = result.style.model_dump_json()
    analysis.design_rules = result.design_rules.model_dump_json()
    analysis.insights = result.insights.model_dump_json() if result.insights else ""
    analysis.analyzed_by = result.analyzed_by
    analysis.model_name = result.analyzed_by
    analysis.prompt = result.prompt
    analysis.review_status = "ai_unverified"
    analysis.version = (analysis.version or 1) + 1

    payload = {
        "basics": result.basics.model_dump(),
        "style": result.style.model_dump(),
        "color": result.color.model_dump(),
        "composition": result.composition.model_dump(),
        "light": result.light.model_dump(),
        "material": result.material,
        "layout": result.layout.model_dump(),
        "typography": result.typography.model_dump(),
        "design_rules": result.design_rules.model_dump(),
        "insights": result.insights.model_dump() if result.insights else None,
        "prompt": result.prompt,
        "summary": result.summary,
        "name": result.name,
        "tags": result.tags,
        "analyzed_by": result.analyzed_by,
    }
    db.add(
        models.AnalysisVersion(
            case_id=case.id,
            version=analysis.version,
            payload=json.dumps(payload, ensure_ascii=False),
            source=source,
            model_name=result.analyzed_by,
            prompt_version=analysis.prompt_version,
        )
    )
    db.commit()
    db.refresh(case)
    return case
