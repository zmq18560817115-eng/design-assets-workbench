"""设计视觉概论——跨案例聚合沉淀层。

把逐张拆解的案例卡，聚合成团队专属的「设计视觉概论」：
分布画像、视觉 DNA、以及从高频共性自动提炼的设计原则；随案例增多越来越准。
"""
from __future__ import annotations

import colorsys
import json
from collections import Counter

from sqlalchemy.orm import Session

from . import config, llm, models

# 素材达到这个量级，概论才比较可信
ENOUGH_THRESHOLD = 5


def _hex_to_family(hexv: str) -> str:
    """把主色 HEX 归成一个粗色系名，用于统计视觉 DNA。"""
    try:
        h = hexv.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return "其他"
    hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if ss < 0.12:
        return "黑" if vv < 0.2 else ("白/浅" if vv > 0.85 else "灰")
    hue = hh * 360
    if hue < 15 or hue >= 345:
        return "红"
    if hue < 45:
        return "橙"
    if hue < 70:
        return "黄"
    if hue < 160:
        return "绿"
    if hue < 200:
        return "青"
    if hue < 255:
        return "蓝"
    if hue < 290:
        return "紫"
    return "品红"


def _dist(counter: Counter, total: int, top: int = 8) -> list[dict]:
    return [
        {"name": name, "count": cnt, "pct": round(cnt / total * 100) if total else 0}
        for name, cnt in counter.most_common(top)
    ]


def _load(analysis: models.Analysis | None) -> dict:
    if not analysis:
        return {}
    def j(s):
        try:
            return json.loads(s or "{}")
        except Exception:
            return {}
    return {
        "layout": j(analysis.layout),
        "typography": j(analysis.typography),
        "style": j(analysis.style),
        "color": j(analysis.color),
    }


def build_concept(db: Session) -> dict:
    cases = db.query(models.Case).all()
    n = len(cases)

    layout_c = Counter()
    align_c = Counter()
    grid_c = Counter()
    style_c = Counter()
    font_c = Counter()
    industry_c = Counter()
    textratio_c = Counter()
    colorfam_c = Counter()
    primary_hex_c = Counter()

    # 分行业聚合
    per_industry: dict[str, dict] = {}

    for c in cases:
        a = _load(c.analysis)
        layout = a.get("layout", {})
        typo = a.get("typography", {})
        style = a.get("style", {})
        color = a.get("color", {})

        lt = layout.get("layout_type", "")
        al = layout.get("alignment", "")
        grid = layout.get("grid_columns", "")
        ft = (typo.get("font_tone", "") or "").split("（")[0].split("/")[0].strip()
        tr = typo.get("text_ratio", "")
        ind = c.industry or "未分类"
        primary = color.get("primary", "")

        if lt:
            layout_c[lt] += 1
        if al:
            align_c[al] += 1
        if grid:
            grid_c[grid] += 1
        if ft:
            font_c[ft] += 1
        if tr:
            textratio_c[tr] += 1
        industry_c[ind] += 1
        for s in style.get("style_tags", []) or []:
            style_c[s] += 1
        if primary:
            primary_hex_c[primary] += 1
            colorfam_c[_hex_to_family(primary)] += 1

        bucket = per_industry.setdefault(
            ind, {"layout": Counter(), "style": Counter(), "colorfam": Counter(), "count": 0}
        )
        bucket["count"] += 1
        if lt:
            bucket["layout"][lt] += 1
        for s in style.get("style_tags", []) or []:
            bucket["style"][s] += 1
        if primary:
            bucket["colorfam"][_hex_to_family(primary)] += 1

    # —— 提炼全局设计原则 ——
    principles: list[str] = []
    if n:
        if layout_c:
            lt, cnt = layout_c.most_common(1)[0]
            principles.append(
                f"版式偏好：{round(cnt / n * 100)}% 的案例采用「{lt}」，是团队最常用的版面骨架。"
            )
        if style_c:
            top_styles = "、".join(s for s, _ in style_c.most_common(3))
            principles.append(f"风格基因：高频风格为 {top_styles}，构成团队视觉调性的主色调。")
        if grid_c:
            g, cnt = grid_c.most_common(1)[0]
            principles.append(f"栅格习惯：最常用 {g}（{round(cnt / n * 100)}%）。")
        if colorfam_c:
            top_col = "、".join(f"{c}" for c, _ in colorfam_c.most_common(3))
            principles.append(f"色彩倾向：主色多落在 {top_col} 色系。")
        if font_c:
            f, _ = font_c.most_common(1)[0]
            principles.append(f"字体调性：以「{f}」为主。")

    # —— 分行业概论 ——
    by_industry = []
    for ind, b in sorted(per_industry.items(), key=lambda x: -x[1]["count"]):
        if b["count"] < 1:
            continue
        top_layout = b["layout"].most_common(1)
        top_styles = [s for s, _ in b["style"].most_common(3)]
        top_cols = [c for c, _ in b["colorfam"].most_common(3)]
        principle = f"「{ind}」共 {b['count']} 例"
        if top_layout:
            principle += f"，多用 {top_layout[0][0]}"
        if top_styles:
            principle += f"，风格偏 {'、'.join(top_styles)}"
        if top_cols:
            principle += f"，主色系 {'、'.join(top_cols)}"
        by_industry.append(
            {
                "industry": ind,
                "count": b["count"],
                "top_layouts": _dist(b["layout"], b["count"], 3),
                "top_styles": top_styles,
                "top_colors": top_cols,
                "principle": principle,
            }
        )

    return {
        "total": n,
        "enough": n >= ENOUGH_THRESHOLD,
        "threshold": ENOUGH_THRESHOLD,
        "distributions": {
            "layout": _dist(layout_c, n),
            "alignment": _dist(align_c, n),
            "grid": _dist(grid_c, n),
            "style": _dist(style_c, n),
            "font": _dist(font_c, n),
            "industry": _dist(industry_c, n),
            "text_ratio": _dist(textratio_c, n),
            "color_family": _dist(colorfam_c, n),
        },
        "visual_dna": {
            "colors": [
                {"hex": hexv, "count": cnt} for hexv, cnt in primary_hex_c.most_common(10)
            ],
            "top_layout": layout_c.most_common(1)[0][0] if layout_c else "",
            "top_style": style_c.most_common(1)[0][0] if style_c else "",
            "top_grid": grid_c.most_common(1)[0][0] if grid_c else "",
        },
        "principles": principles,
        "by_industry": by_industry,
    }


def _digest(data: dict) -> str:
    """把聚合数据压成给模型的简要文字，控制 token。"""
    d = data["distributions"]

    def fmt(items):
        return "、".join(f"{x['name']}({x['pct']}%)" for x in items[:5]) or "无"

    lines = [
        f"案例总数：{data['total']}",
        f"版式分布：{fmt(d['layout'])}",
        f"风格分布：{fmt(d['style'])}",
        f"栅格分布：{fmt(d['grid'])}",
        f"色系分布：{fmt(d['color_family'])}",
        f"行业分布：{fmt(d['industry'])}",
        f"字体调性：{fmt(d['font'])}",
        "分行业：" + "；".join(b["principle"] for b in data["by_industry"][:6]),
    ]
    return "\n".join(lines)


def synthesize_methodology(data: dict) -> dict:
    """用文本模型把聚合数据写成成体系的设计方法论（需配置 LLM）。"""
    if not config.llm_enabled():
        return {"enabled": False, "methodology": ""}
    if data.get("total", 0) == 0:
        return {"enabled": True, "methodology": "", "note": "暂无案例，无法生成方法论。"}

    digest = _digest(data)
    messages = [
        {
            "role": "system",
            "content": "你是资深设计总监，擅长把团队的视觉数据提炼成成体系、可执行的设计方法论。",
        },
        {
            "role": "user",
            "content": (
                "以下是我们团队案例库拆解后的聚合统计，请据此写一份**该团队专属的设计视觉方法论**。"
                "要求：成体系、有洞察、可落地；结合具体数据、避免空话；**精炼，控制在 900 字以内**。"
                "用 Markdown，包含『整体视觉基调』『版式与栅格规范』『色彩与字体基因』"
                "『分场景/行业建议』『可复用的设计原则清单』几个小节。\n\n"
                f"【聚合统计】\n{digest}"
            ),
        },
    ]
    text = llm.chat(messages, temperature=0.5, max_tokens=1200)
    return {"enabled": True, "methodology": text, "model": config.LLM_MODEL}
