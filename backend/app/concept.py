"""Weighted company visual profile built from reviewed cases and preferences."""
from __future__ import annotations

import colorsys
import json
from collections import Counter, defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import config, llm, models

ENOUGH_THRESHOLD = 20
TRUST_WEIGHTS = {
    "ai_unverified": 0.25,
    "verified": 2.0,
    "company_recommended": 4.0,
    "rejected": 0.0,
}
PREFERENCE_WEIGHTS = {
    "like": 0.5,
    "favorite": 0.75,
    "selected": 1.0,
    "adopt": 1.5,
    "published": 2.0,
    "dislike": -1.0,
    "reject": -1.5,
}


def _hex_to_family(value: str) -> str:
    try:
        value = value.lstrip("#")
        r, g, b = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except Exception:
        return "其他"
    hue, saturation, brightness = colorsys.rgb_to_hsv(
        r / 255, g / 255, b / 255
    )
    if saturation < 0.12:
        if brightness < 0.2:
            return "黑色"
        if brightness > 0.85:
            return "白/浅色"
        return "灰色"
    degree = hue * 360
    if degree < 15 or degree >= 345:
        return "红色"
    if degree < 45:
        return "橙色"
    if degree < 70:
        return "黄色"
    if degree < 160:
        return "绿色"
    if degree < 200:
        return "青色"
    if degree < 255:
        return "蓝色"
    if degree < 290:
        return "紫色"
    return "品红"


def _load(analysis: models.Analysis | None) -> dict:
    if not analysis:
        return {}

    def parse(value: str) -> dict:
        try:
            return json.loads(value or "{}")
        except Exception:
            return {}

    return {
        "layout": parse(analysis.layout),
        "typography": parse(analysis.typography),
        "style": parse(analysis.style),
        "color": parse(analysis.color),
    }


def _distribution(counter: Counter, total: float, top: int = 8) -> list[dict]:
    return [
        {
            "name": name,
            "count": round(weight, 2),
            "pct": round(weight / total * 100) if total else 0,
        }
        for name, weight in counter.most_common(top)
    ]


def _preference_map(db: Session) -> dict[int, dict[str, int]]:
    rows = (
        db.query(
            models.PreferenceEvent.case_id,
            models.PreferenceEvent.event_type,
            func.sum(models.PreferenceEvent.value),
        )
        .group_by(
            models.PreferenceEvent.case_id,
            models.PreferenceEvent.event_type,
        )
        .all()
    )
    result: dict[int, dict[str, int]] = defaultdict(dict)
    for case_id, event_type, value in rows:
        result[case_id][event_type] = int(value or 0)
    return result


def _case_weight(case: models.Case, preferences: dict[str, int]) -> float:
    weight = TRUST_WEIGHTS.get(case.trust_status or "ai_unverified", 0.25)
    if (
        case.trust_status == "ai_unverified"
        and case.image
        and case.image.source_type == "company_published"
    ):
        weight = 1.0
    if case.project and case.project.is_gold:
        weight *= 1.5
    for event_type, count in preferences.items():
        weight += PREFERENCE_WEIGHTS.get(event_type, 0.0) * count
    return max(0.0, weight)


def build_concept(
    db: Session,
    business_line: str = "",
    asset_category: str = "",
) -> dict:
    """Aggregate a company profile, prioritizing trusted business evidence."""
    cases = db.query(models.Case).all()
    scope = business_line.strip()
    if scope:
        cases = [
            case
            for case in cases
            if (case.business_line or case.industry or "").strip() == scope
        ]
    category_scope = asset_category.strip()
    if category_scope:
        cases = [
            case for case in cases if (case.asset_category or "layout") == category_scope
        ]
    run_query = db.query(models.ServiceRun)
    if scope:
        run_query = run_query.filter(models.ServiceRun.industry == scope)
    if category_scope:
        run_query = run_query.filter(models.ServiceRun.focus_category == category_scope)
    service_runs = run_query.all()
    adopted_runs = sum(1 for run in service_runs if run.status == "adopted")
    case_ids = {case.id for case in cases}
    keep_counter = Counter()
    avoid_counter = Counter()
    if case_ids:
        reviews = (
            db.query(models.CaseReview)
            .filter(models.CaseReview.case_id.in_(case_ids))
            .all()
        )
        for review in reviews:
            for value, counter in (
                (review.keep_reasons, keep_counter),
                (review.avoid_reasons, avoid_counter),
            ):
                try:
                    items = json.loads(value or "[]")
                except Exception:
                    items = []
                counter.update(
                    item.strip()
                    for item in items
                    if isinstance(item, str) and item.strip()
                )
    preferences = _preference_map(db)
    trust_counts = Counter(case.trust_status or "ai_unverified" for case in cases)

    layout_counter = Counter()
    alignment_counter = Counter()
    grid_counter = Counter()
    style_counter = Counter()
    font_counter = Counter()
    industry_counter = Counter()
    text_ratio_counter = Counter()
    color_family_counter = Counter()
    primary_counter = Counter()
    category_weights = Counter()
    per_industry: dict[str, dict] = {}
    weighted_total = 0.0
    contributing_cases = 0

    for case in cases:
        weight = _case_weight(case, preferences.get(case.id, {}))
        if weight <= 0:
            continue
        contributing_cases += 1
        weighted_total += weight
        category_weights[case.asset_category or "layout"] += weight

        analysis = _load(case.analysis)
        layout = analysis.get("layout", {})
        typography = analysis.get("typography", {})
        style = analysis.get("style", {})
        color = analysis.get("color", {})

        layout_type = layout.get("layout_type", "")
        alignment = layout.get("alignment", "")
        grid = layout.get("grid_columns", "")
        font = (typography.get("font_tone", "") or "").split("，")[0].split("/")[0].strip()
        text_ratio = typography.get("text_ratio", "")
        industry = case.business_line or case.industry or "未分类"
        primary = color.get("primary", "")

        if layout_type:
            layout_counter[layout_type] += weight
        if alignment:
            alignment_counter[alignment] += weight
        if grid:
            grid_counter[grid] += weight
        if font:
            font_counter[font] += weight
        if text_ratio:
            text_ratio_counter[text_ratio] += weight
        industry_counter[industry] += weight
        for tag in style.get("style_tags", []) or []:
            style_counter[tag] += weight
        if primary:
            primary_counter[primary] += weight
            color_family_counter[_hex_to_family(primary)] += weight

        bucket = per_industry.setdefault(
            industry,
            {
                "layout": Counter(),
                "style": Counter(),
                "color": Counter(),
                "weight": 0.0,
                "cases": 0,
            },
        )
        bucket["weight"] += weight
        bucket["cases"] += 1
        if layout_type:
            bucket["layout"][layout_type] += weight
        for tag in style.get("style_tags", []) or []:
            bucket["style"][tag] += weight
        if primary:
            bucket["color"][_hex_to_family(primary)] += weight

    principles = []
    if weighted_total:
        if layout_counter:
            name, weight = layout_counter.most_common(1)[0]
            principles.append(
                f"版式偏好：加权证据中 {round(weight / weighted_total * 100)}% "
                f"指向「{name}」。"
            )
        if style_counter:
            names = "、".join(name for name, _ in style_counter.most_common(3))
            principles.append(
                f"风格基因：高权重风格为 {names}，优先反映人工确认、公司推荐与采用行为。"
            )
        if grid_counter:
            name, weight = grid_counter.most_common(1)[0]
            principles.append(
                f"栅格习惯：最常用 {name}，加权占比 "
                f"{round(weight / weighted_total * 100)}%。"
            )
        if color_family_counter:
            names = "、".join(name for name, _ in color_family_counter.most_common(3))
            principles.append(f"色彩倾向：高权重案例主要使用 {names} 色系。")
        if font_counter:
            principles.append(f"字体调性：以「{font_counter.most_common(1)[0][0]}」为主。")

    by_industry = []
    for industry, bucket in sorted(
        per_industry.items(), key=lambda item: -item[1]["weight"]
    ):
        top_layout = bucket["layout"].most_common(1)
        top_styles = [name for name, _ in bucket["style"].most_common(3)]
        top_colors = [name for name, _ in bucket["color"].most_common(3)]
        parts = [f"「{industry}」包含 {bucket['cases']} 个有效案例"]
        if top_layout:
            parts.append(f"版式偏好 {top_layout[0][0]}")
        if top_styles:
            parts.append(f"风格偏好 {'、'.join(top_styles)}")
        if top_colors:
            parts.append(f"色彩偏好 {'、'.join(top_colors)}")
        by_industry.append(
            {
                "industry": industry,
                "count": bucket["cases"],
                "weighted_count": round(bucket["weight"], 2),
                "top_layouts": _distribution(
                    bucket["layout"], bucket["weight"], 3
                ),
                "top_styles": top_styles,
                "top_colors": top_colors,
                "principle": "；".join(parts),
            }
        )

    trusted_count = (
        trust_counts.get("verified", 0)
        + trust_counts.get("company_recommended", 0)
    )
    company_published_count = sum(
        1
        for case in cases
        if case.image and case.image.source_type == "company_published"
    )
    model_analyzed_count = sum(
        1
        for case in cases
        if case.analysis
        and case.analysis.model_name
        and case.analysis.model_name != "启发式规则"
    )
    evidence_count = sum(
        1
        for case in cases
        if case.trust_status in {"verified", "company_recommended"}
        or (case.image and case.image.source_type == "company_published")
    )
    return {
        "scope": " / ".join(
            part for part in [scope or "company", category_scope] if part
        ),
        "business_line": scope,
        "asset_category": category_scope,
        "total": len(cases),
        "contributing_cases": contributing_cases,
        "weighted_total": round(weighted_total, 2),
        "enough": trusted_count >= ENOUGH_THRESHOLD,
        "threshold": ENOUGH_THRESHOLD,
        "trusted_count": trusted_count,
        "company_published_count": company_published_count,
        "model_analyzed_count": model_analyzed_count,
        "evidence_count": evidence_count,
        "service_run_count": len(service_runs),
        "adopted_run_count": adopted_runs,
        "trust_counts": dict(trust_counts),
        "category_weights": {
            key: round(value, 2) for key, value in category_weights.items()
        },
        "weight_rules": {
            "trust": TRUST_WEIGHTS,
            "preference": PREFERENCE_WEIGHTS,
            "gold_project_multiplier": 1.5,
        },
        "distributions": {
            "layout": _distribution(layout_counter, weighted_total),
            "alignment": _distribution(alignment_counter, weighted_total),
            "grid": _distribution(grid_counter, weighted_total),
            "style": _distribution(style_counter, weighted_total),
            "font": _distribution(font_counter, weighted_total),
            "industry": _distribution(industry_counter, weighted_total),
            "text_ratio": _distribution(text_ratio_counter, weighted_total),
            "color_family": _distribution(color_family_counter, weighted_total),
        },
        "visual_dna": {
            "colors": [
                {"hex": value, "count": round(weight, 2)}
                for value, weight in primary_counter.most_common(10)
            ],
            "top_layout": layout_counter.most_common(1)[0][0]
            if layout_counter
            else "",
            "top_style": style_counter.most_common(1)[0][0]
            if style_counter
            else "",
            "top_grid": grid_counter.most_common(1)[0][0] if grid_counter else "",
        },
        "principles": principles,
        "by_industry": by_industry,
        "explicit_guidance": {
            "keep": [
                {"text": text, "count": count}
                for text, count in keep_counter.most_common(10)
            ],
            "avoid": [
                {"text": text, "count": count}
                for text, count in avoid_counter.most_common(10)
            ],
        },
    }


def _digest(data: dict) -> str:
    distributions = data["distributions"]

    def format_items(items: list[dict]) -> str:
        return "、".join(
            f"{item['name']}({item['pct']}%)" for item in items[:5]
        ) or "无"

    return "\n".join(
        [
            f"原始案例：{data['total']}",
            f"人工可信案例：{data['trusted_count']}",
            f"加权证据量：{data['weighted_total']}",
            f"版式：{format_items(distributions['layout'])}",
            f"风格：{format_items(distributions['style'])}",
            f"栅格：{format_items(distributions['grid'])}",
            f"色系：{format_items(distributions['color_family'])}",
            f"业务线：{format_items(distributions['industry'])}",
            "分业务线：" + "；".join(
                item["principle"] for item in data["by_industry"][:6]
            ),
        ]
    )


def recommendation_context(data: dict, industry: str = "") -> dict:
    """Return a compact, evidence-labelled company preference context."""
    distributions = data.get("distributions") or {}

    def names(key: str, limit: int = 3) -> list[str]:
        return [
            str(item.get("name"))
            for item in (distributions.get(key) or [])[:limit]
            if item.get("name")
        ]

    trusted = int(data.get("trusted_count") or 0)
    evidence_count = int(data.get("evidence_count") or trusted)
    evidence_level = (
        "strong"
        if evidence_count >= 30
        else "growing"
        if evidence_count >= 10
        else "insufficient"
    )
    industry_profile = next(
        (
            item
            for item in (data.get("by_industry") or [])
            if industry and item.get("industry") == industry
        ),
        None,
    )
    guidance = data.get("explicit_guidance") or {}
    service_runs = int(data.get("service_run_count") or 0)
    adopted_runs = int(data.get("adopted_run_count") or 0)
    recommended_cases = int(
        (data.get("trust_counts") or {}).get("company_recommended") or 0
    )
    usage_mode = (
        "operational"
        if trusted >= 3
        and recommended_cases >= 1
        and service_runs >= 5
        and adopted_runs >= 2
        else "pilot"
        if trusted >= 3 and recommended_cases >= 1
        else "reference_only"
    )
    return {
        "scope": data.get("scope") or "company",
        "applied": evidence_count > 0,
        "evidence_level": evidence_level,
        "trusted_cases": trusted,
        "company_published_cases": int(data.get("company_published_count") or 0),
        "model_analyzed_cases": int(data.get("model_analyzed_count") or 0),
        "evidence_cases": evidence_count,
        "service_runs": service_runs,
        "adopted_runs": adopted_runs,
        "usage_mode": usage_mode,
        "layouts": names("layout"),
        "styles": names("style"),
        "grids": names("grid"),
        "fonts": names("font"),
        "color_families": names("color_family"),
        "keep_rules": [
            item.get("text")
            for item in (guidance.get("keep") or [])[:5]
            if item.get("text")
        ],
        "avoid_rules": [
            item.get("text")
            for item in (guidance.get("avoid") or [])[:5]
            if item.get("text")
        ],
        "industry_profile": industry_profile,
    }


def synthesize_methodology(data: dict) -> dict:
    if not config.llm_enabled():
        return {"enabled": False, "methodology": ""}
    if data.get("weighted_total", 0) == 0:
        return {
            "enabled": True,
            "methodology": "",
            "note": "暂无有效案例，无法生成方法论。",
        }
    text = llm.chat(
        [
            {
                "role": "system",
                "content": (
                    "你是资深设计总监。只根据加权公司证据总结视觉方法论，"
                    "明确区分稳定偏好与证据不足的推测。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请基于以下统计输出900字以内的公司视觉方法论，使用Markdown，"
                    "包括整体视觉基调、版式与栅格、色彩与字体、分业务线建议、"
                    "可复用原则和禁用项。\n\n"
                    + _digest(data)
                ),
            },
        ],
        temperature=0.4,
        max_tokens=1200,
    )
    return {"enabled": True, "methodology": text, "model": config.LLM_MODEL}
