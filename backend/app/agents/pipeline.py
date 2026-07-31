"""AI Agent 流水线编排。

串联 Vision → Style → Design → Layout → Rule → Prompt 六个 Agent，
输出技术方案「六、AI输出结构」定义的完整拆解结果
（含色彩、构图、光影、材质、排版、文字/标题/字体）。
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from .. import config, vlm
from ..asset_categories import category_label, normalize_category
from ..schemas import AnalysisResult, DeepInsights
from ..vision_provider import analyze
from . import (
    design_agent,
    layout_agent,
    prompt_agent,
    rule_agent,
    style_agent,
    vision_agent,
)


def _vlm_enabled() -> bool:
    return config.vlm_enabled()


def run_pipeline(
    image_path: str,
    asset_category: str = "layout",
    enable_vlm: bool = True,
    strict_vlm: bool = False,
    layout_few_shots: list[dict] | None = None,
) -> AnalysisResult:
    asset_category = normalize_category(asset_category)
    features = analyze(image_path)

    basics = vision_agent.run(features)
    style = style_agent.run(features)
    color, composition, light, material = design_agent.run(features)
    layout, typography = layout_agent.run(features)
    rules = rule_agent.run(
        features, basics, style, color, composition, light, layout, typography
    )
    prompt = prompt_agent.run(
        features, basics, style, color, light, material, layout, typography
    )

    # 案例名称与总结 —— 以「排版」为拆解重心（排版优先，风格次之）
    name = f"{layout.layout_type}·{basics.industry}·{'/'.join(style.style_tags[:1])}案例"
    summary = (
        f"一张{basics.image_type}，排版为{layout.layout_type}（{layout.alignment}），"
        f"信息层级：{' → '.join(layout.hierarchy)}；{typography.text_ratio}，"
        f"{typography.title_treatment}。风格上呈现{'、'.join(style.style_tags)}，{color.description}"
    )

    # 汇总标签（供检索）—— 排版/文字维度置前，风格维度置后
    tags = list(
        dict.fromkeys(
            [
                layout.layout_type,
                layout.alignment,
                typography.text_ratio,
                typography.font_tone.split("（")[0].split("/")[0].strip(),
                composition.type,
            ]
            + style.style_tags
            + style.mood_keywords
            + [basics.industry, basics.scene, light.type]
        )
    )

    result = AnalysisResult(
        basics=basics,
        style=style,
        color=color,
        composition=composition,
        light=light,
        material=material,
        layout=layout,
        typography=typography,
        design_rules=rules,
        prompt=prompt,
        summary=summary,
        name=name,
        tags=tags,
    )

    # 若配置了真实视觉大模型，用其语义理解增强结果（硬参数仍保留 Pillow 测量值）
    if enable_vlm and _vlm_enabled():
        try:
            result = _augment_with_vlm(
                image_path,
                features,
                result,
                asset_category,
                layout_few_shots=layout_few_shots,
            )
        except Exception:
            if strict_vlm:
                raise
            # 大模型不可用时静默回退到启发式结果，保证链路不中断
            pass

    return result


def _augment_with_vlm(
    image_path,
    features,
    result: AnalysisResult,
    asset_category: str = "layout",
    layout_few_shots: list[dict] | None = None,
) -> AnalysisResult:
    """用视觉大模型的语义输出覆盖启发式结果，保留 Pillow 的硬版式/色板参数。"""
    data = Path(image_path).read_bytes()
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    hints = {
        "palette": features.palette,
        "tone": ("暖调" if features.warm else "冷调") + f"，亮度{features.brightness}",
        "grid_columns": result.layout.grid_columns,
        "modules": result.layout.modules,
        "margins": result.layout.margins,
        "layout_few_shots": layout_few_shots or [],
    }
    v = vlm.analyze_image(data, mime, hints, asset_category=asset_category)

    def pick(key: str, fallback):
        val = v.get(key)
        return val if val else fallback

    r = result
    # 基础信息
    r.basics.image_type = pick("image_type", r.basics.image_type)
    r.basics.industry = pick("industry", r.basics.industry)
    r.basics.scene = pick("scene", r.basics.scene)
    # 风格
    r.style.style_tags = pick("style_tags", r.style.style_tags)
    r.style.mood_keywords = pick("mood_keywords", r.style.mood_keywords)
    r.style.brand_position = pick("brand_position", r.style.brand_position)
    # 排版语义（硬参数 grid/margins 不动）
    r.layout.layout_type = pick("layout_type", r.layout.layout_type)
    r.layout.alignment = pick("alignment", r.layout.alignment)
    r.layout.hierarchy = pick("hierarchy", r.layout.hierarchy)
    r.layout.canvas_ratio = pick("canvas_ratio", r.layout.canvas_ratio)
    r.layout.orientation = pick("orientation", r.layout.orientation)
    r.layout.reading_flow = pick("reading_flow", r.layout.reading_flow)
    r.layout.focal_region = pick("focal_region", r.layout.focal_region)
    r.layout.information_density = pick(
        "information_density", r.layout.information_density
    )
    r.layout.text_image_ratio = v.get(
        "text_image_ratio", r.layout.text_image_ratio
    )
    r.layout.blueprint_modules = v.get("blueprint_modules") or []
    r.layout.layout_summary = pick("layout_summary", r.layout.layout_summary)
    # 文字
    r.typography.title_treatment = pick("title_treatment", r.typography.title_treatment)
    r.typography.font_tone = pick("font_tone", r.typography.font_tone)
    # 设计规则
    r.design_rules.why_good = pick("why_good", r.design_rules.why_good)
    r.design_rules.reusable_methods = pick(
        "reusable_methods", r.design_rules.reusable_methods
    )
    # 提示词 / 总结
    if v.get("prompt_zh"):
        en = v.get("prompt_en", "")
        r.prompt = v["prompt_zh"] + (f"\n\nEN: {en}" if en else "")
    r.summary = pick("summary", r.summary)

    # 深度解析
    r.insights = DeepInsights(
        target_audience=v.get("target_audience", ""),
        applicable_scenes=v.get("applicable_scenes", []) or [],
        color_roles=v.get("color_roles", []) or [],
        composition_principles=v.get("composition_principles", []) or [],
        emotion_narrative=v.get("emotion_narrative", ""),
        critique=v.get("critique", []) or [],
        improvement=v.get("improvement", []) or [],
    )
    r.analyzed_by = config.VISION_MODEL or config.VISION_PROVIDER

    # 名称与标签基于（可能被覆盖的）语义重算，保持排版优先
    r.name = (
        f"{category_label(asset_category)}·{r.layout.layout_type}·"
        f"{'/'.join(r.style.style_tags[:1])}案例"
    )
    r.tags = list(
        dict.fromkeys(
            [r.layout.layout_type, r.layout.alignment, r.typography.text_ratio]
            + r.style.style_tags
            + r.style.mood_keywords
            + [r.basics.industry, r.basics.scene]
        )
    )
    return r
