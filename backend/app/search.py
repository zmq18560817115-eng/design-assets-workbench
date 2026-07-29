"""第一阶段多模态检索。

在 100～500 张素材规模下，先用结构化视觉字段完成可解释的混合召回：
文本、业务筛选、标签与参考图拆解共同计分。接口与结果结构保持稳定，后续可将
候选召回替换为 pgvector / 专用向量库，而不改前端交互。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import crud, models
from .schemas import AnalysisResult


@dataclass
class RankedCase:
    case: models.Case
    score: float
    reasons: list[str]


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"[\s,，。；;、/|]+", " ", (text or "").lower()).strip()
    if not normalized:
        return []
    words = normalized.split()
    # 中文无空格需求额外加入连续二字片段，提高“温暖母婴”等短语召回。
    compact = "".join(words)
    if any("\u4e00" <= ch <= "\u9fff" for ch in compact):
        words.extend(compact[i : i + 2] for i in range(max(0, len(compact) - 1)))
    return list(dict.fromkeys(x for x in words if x))


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    value = (value or "").strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _color_similarity(left: str, right: str) -> float:
    a, b = _hex_rgb(left), _hex_rgb(right)
    if not a or not b:
        return 0.0
    distance = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return max(0.0, 1.0 - distance / 441.7)


def _analysis(case: models.Case) -> dict:
    return crud.analysis_to_dict(case.analysis) or {}


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).lower()


def _reference_score(case: models.Case, ref: AnalysisResult) -> tuple[float, list[str]]:
    a = _analysis(case)
    reasons: list[str] = []
    score = 0.0

    layout = a.get("layout") or {}
    typography = a.get("typography") or {}
    style = a.get("style") or {}
    color = a.get("color") or {}

    if layout.get("layout_type") == ref.layout.layout_type:
        score += 13
        reasons.append("版式类型接近")
    if layout.get("alignment") == ref.layout.alignment:
        score += 5
        reasons.append("对齐方式一致")
    if layout.get("grid_columns") == ref.layout.grid_columns:
        score += 5
        reasons.append("栅格结构相似")
    if typography.get("text_ratio") == ref.typography.text_ratio:
        score += 4
        reasons.append("图文占比接近")

    case_styles = set(style.get("style_tags") or [])
    ref_styles = set(ref.style.style_tags)
    overlap = case_styles & ref_styles
    if overlap:
        score += min(10, 5 * len(overlap))
        reasons.append(f"共同风格：{'、'.join(sorted(overlap))}")

    case_moods = set(style.get("mood_keywords") or [])
    ref_moods = set(ref.style.mood_keywords)
    mood_overlap = case_moods & ref_moods
    if mood_overlap:
        score += min(5, 2.5 * len(mood_overlap))
        reasons.append(f"情绪接近：{'、'.join(sorted(mood_overlap))}")

    sim = _color_similarity(color.get("primary", ""), ref.color.primary)
    if sim >= 0.6:
        score += round(sim * 8, 2)
        reasons.append("主色倾向接近")

    if getattr(case, "content_type", "") == ref.basics.image_type:
        score += 4
        reasons.append("内容类型一致")
    return score, reasons


def search_cases(
    db: Session,
    *,
    query_text: str = "",
    product: str = "",
    scene: str = "",
    content_type: str = "",
    source_type: str = "",
    tags: list[str] | None = None,
    reference: AnalysisResult | None = None,
    limit: int = 60,
) -> list[RankedCase]:
    """返回可解释的混合排序结果。"""
    query = db.query(models.Case).join(models.Case.image)
    if product:
        query = query.filter(models.Case.product_category == product)
    if scene:
        query = query.filter(models.Case.scene == scene)
    if content_type:
        query = query.filter(models.Case.content_type == content_type)
    if source_type:
        query = query.filter(models.Image.source_type == source_type)

    cases = query.order_by(models.Case.created_at.desc()).all()
    preference_rows = (
        db.query(
            models.PreferenceEvent.case_id,
            models.PreferenceEvent.event_type,
            models.PreferenceEvent.value,
        )
        .all()
    )
    preference_scores: dict[int, float] = {}
    preference_weights = {
        "like": 2.0,
        "favorite": 3.0,
        "selected": 4.0,
        "adopt": 6.0,
        "published": 8.0,
        "dislike": -4.0,
        "reject": -8.0,
    }
    for case_id, event_type, value in preference_rows:
        preference_scores[case_id] = preference_scores.get(case_id, 0.0) + (
            preference_weights.get(event_type, 0.0) * (value or 0)
        )
    wanted_tags = {x.strip() for x in (tags or []) if x.strip()}
    tokens = _tokens(query_text)
    ranked: list[RankedCase] = []

    for case in cases:
        if case.trust_status == "rejected":
            continue
        reasons: list[str] = []
        score = 1.0
        tag_names = {tag.name for tag in case.tags}
        analysis = _analysis(case)
        haystack = " ".join(
            [
                case.name or "",
                case.summary or "",
                case.industry or "",
                case.scene or "",
                getattr(case, "product_category", "") or "",
                getattr(case, "content_type", "") or "",
                " ".join(tag_names),
                _json_text(analysis),
            ]
        ).lower()

        if tokens:
            matched = [token for token in tokens if token in haystack]
            if not matched:
                continue
            score += min(38, 7 * len(matched))
            reasons.append(f"匹配需求：{'、'.join(matched[:4])}")

        if wanted_tags:
            overlap = wanted_tags & tag_names
            if not overlap:
                continue
            score += min(22, 7 * len(overlap))
            reasons.append(f"匹配标签：{'、'.join(sorted(overlap))}")

        if product:
            score += 8
            reasons.append("产品匹配")
        if scene:
            score += 6
            reasons.append("场景匹配")
        if content_type:
            score += 6
            reasons.append("内容类型匹配")
        if source_type:
            score += 4
            reasons.append("来源匹配")

        if reference is not None:
            ref_score, ref_reasons = _reference_score(case, reference)
            # 有参考图时过滤完全无视觉相似信号的候选。
            if ref_score <= 0 and not tokens and not wanted_tags:
                continue
            score += ref_score
            reasons.extend(ref_reasons)

        trust_bonus = {
            "company_recommended": 18.0,
            "verified": 10.0,
            "ai_unverified": 0.0,
        }.get(case.trust_status, 0.0)
        if trust_bonus:
            score += trust_bonus
            reasons.insert(
                0,
                "公司推荐样本"
                if case.trust_status == "company_recommended"
                else "人工确认样本"
            )
        if case.project and case.project.is_gold and trust_bonus:
            score += 4.0
            reasons.insert(1, "黄金项目证据")
        preference_bonus = max(-12.0, min(16.0, preference_scores.get(case.id, 0.0)))
        if preference_bonus:
            score += preference_bonus
            reasons.insert(
                0,
                "真实业务采用信号" if preference_bonus > 0 else "存在负向业务反馈"
            )

        ranked.append(
            RankedCase(
                case=case,
                score=round(min(score, 100.0), 2),
                reasons=reasons[:5] or ["近期入库案例"],
            )
        )

    ranked.sort(key=lambda item: (item.score, item.case.created_at), reverse=True)
    return ranked[: max(1, min(limit, 100))]
