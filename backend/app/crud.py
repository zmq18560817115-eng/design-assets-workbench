"""数据持久化与查询逻辑。"""
from __future__ import annotations

import json
import datetime as dt

from sqlalchemy.orm import Session

from . import models
from .schemas import AnalysisResult, CaseReviewInput


def get_or_create_tag(db: Session, name: str, category: str = "style") -> models.Tag:
    name = name.strip()
    tag = db.query(models.Tag).filter(models.Tag.name == name).first()
    if not tag:
        tag = models.Tag(name=name, category=category)
        db.add(tag)
        db.flush()
    return tag


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
) -> list[models.Case]:
    query = db.query(models.Case)
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

    payload = {
        "case": {
            "name": case.name,
            "summary": case.summary,
            "business_line": case.business_line,
            "channel": case.channel,
            "campaign_stage": case.campaign_stage,
            "business_goal": case.business_goal,
            "review_decision": case.review_decision,
            "review_notes": case.review_notes,
            "trust_status": case.trust_status,
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
    db.commit()
    db.refresh(case)
    return case
