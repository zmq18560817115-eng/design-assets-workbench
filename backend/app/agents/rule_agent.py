"""Rule Agent —— 总结设计规律。

对应技术方案「五、AI Agent流程 4. Rule Agent」与「六、设计规则」：
输出「为什么优秀」与「可复用方法」。
"""
from __future__ import annotations

from ..schemas import (
    CaseBasics,
    ColorSystem,
    Composition,
    DesignRules,
    Layout,
    Light,
    Typography,
    VisualStyle,
)
from ..vision_provider import ImageFeatures


def run(
    features: ImageFeatures,
    basics: CaseBasics,
    style: VisualStyle,
    color: ColorSystem,
    composition: Composition,
    light: Light,
    layout: Layout,
    typography: Typography,
) -> DesignRules:
    why: list[str] = []
    methods: list[str] = []

    # 为什么优秀
    if len(features.palette) <= 3 or features.saturation < 0.35:
        why.append("色彩克制统一，避免了视觉噪音，画面高级且聚焦。")
        methods.append(f"控制主色在 2~3 种以内，以 {color.primary} 为核心色。")
    if features.contrast > 0.45:
        why.append("明暗对比强化了主体，视觉引导清晰。")
        methods.append("用高对比制造焦点，把最亮/最暗留给核心信息。")
    else:
        why.append("柔和层次营造了舒适、耐看的观感。")
        methods.append("用相近明度过渡与留白，营造呼吸感。")

    why.append(f"{'、'.join(style.style_tags)}的风格与「{basics.industry}」定位高度契合。")

    # 排版 / 文字层面的规律
    if "留白" in layout.layout_type or "中轴" in layout.layout_type:
        why.append(f"{layout.layout_type}让信息主次分明，标题—正文层级清晰、阅读不费力。")
    else:
        why.append(f"{layout.layout_type}承载了较大信息量却不显杂乱，靠对齐与层级维持了秩序。")
    why.append(f"文字采用{typography.title_treatment}，{typography.size_contrast}，强化了信息层级。")

    methods.append(f"复用 {composition.type} 的构图与 {light.type} 的光影，保持系列一致性。")
    methods.append(f"排版沿用「{layout.layout_type} + {layout.alignment}」，信息层级：{' → '.join(layout.hierarchy)}。")
    methods.append(f"标题处理：{typography.title_treatment}；字体调性统一为「{typography.font_tone}」。")
    methods.append(f"沿用情绪关键词「{ '、'.join(style.mood_keywords) }」统一整套视觉语气。")

    return DesignRules(why_good=why, reusable_methods=methods)
