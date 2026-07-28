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
        f"{p['zh']}的白板版式图（{basics.industry}）",
        f"排版：{layout.layout_type}，{layout.grid_columns}，{layout.alignment}，{layout.margins}",
        f"信息层级：{' → '.join(layout.hierarchy)}，{layout.modules}，{layout.spacing}",
        f"文字：{typography.title_treatment}，字体{typography.font_tone}",
        f"风格参考：{'、'.join(style.style_tags)}；情绪：{'、'.join(style.mood_keywords)}",
        f"少量配色注释：{'、'.join(features.color_names[:3]) or '中性色'}，主色 {color.primary}",
        "白色或浅灰画布，灰阶模块、线框、占位图片框和占位文字，清楚展示网格、页边距、留白与阅读动线",
        "低保真、可编辑的版式骨架，不生成完整文案、品牌Logo或成品摄影渲染",
    ]
    zh = "，".join(x for x in zh_parts if x)

    en = (
        f"whiteboard layout wireframe for {p['en']}, {basics.industry} industry, "
        f"{layout.layout_type} layout, {layout.grid_columns}, {layout.alignment}, "
        f"clear information hierarchy and reading flow, {layout.margins}, "
        f"white or light-gray canvas, grayscale modules, image placeholders, text placeholders, "
        f"grid and spacing annotations, {', '.join(style.style_tags)} style references, "
        f"minimal accent color {color.primary}, editable low-fidelity composition skeleton, "
        "no final copy, no brand logo, no polished photography rendering"
    )
    return f"{zh}\n\nEN: {en}"
