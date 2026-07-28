"""Prompt Agent —— 生成 AI 绘图提示词。

对应技术方案「五、AI Agent流程 5. Prompt Agent」。
将拆解结果反向组合成可直接用于 AI 绘图的提示词，
并**贴合原图的平台/媒介类型**（UI/网页/海报/电商…），避免一律套电商话术。
"""
from __future__ import annotations

from .. import platform as plat
from ..schemas import CaseBasics, ColorSystem, Layout, Light, Typography, VisualStyle
from ..vision_provider import ImageFeatures


def run(
    features: ImageFeatures,
    basics: CaseBasics,
    style: VisualStyle,
    color: ColorSystem,
    light: Light,
    material: str,
    layout: Layout,
    typography: Typography,
) -> str:
    # 识别平台类型，选用对应平台的设计语言与质量后缀
    p = plat.style_of(basics.image_type, features.orientation, basics.scene)
    tone = "warm tones" if features.warm else "cool tones"

    zh_parts = [
        f"{p['zh']}（{basics.industry}）",
        "、".join(style.style_tags),
        f"色彩：{'、'.join(features.color_names[:3]) or '中性色'}（{tone}），主色 {color.primary}",
        f"排版：{layout.layout_type}，{layout.grid_columns}，{layout.alignment}，{layout.margins}",
        f"文字：{typography.title_treatment}，字体{typography.font_tone}",
        f"光影：{light.type}",
        f"情绪：{'、'.join(style.mood_keywords)}",
        p["quality"],
    ]
    zh = "，".join(x for x in zh_parts if x)

    en = (
        f"{p['en']}, {basics.industry} industry, {', '.join(style.style_tags)} style, "
        f"{tone}, primary color {color.primary}, "
        f"{layout.layout_type} layout, {layout.alignment}, clear typographic hierarchy, "
        f"{light.type} lighting, {', '.join(style.mood_keywords)} mood, {p['quality']}"
    )
    return f"{zh}\n\nEN: {en}"
