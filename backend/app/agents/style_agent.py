"""Style Agent —— 分析视觉风格。

对应技术方案「五、AI Agent流程 2. Style Agent」：
输出高级感、科技感、温暖感、年轻化等风格标签与情绪关键词。
"""
from __future__ import annotations

from ..schemas import VisualStyle
from ..vision_provider import ImageFeatures


def run(features: ImageFeatures) -> VisualStyle:
    style_tags: list[str] = []
    mood: list[str] = []

    # 高级感：低饱和 + 高对比 或 暗调
    if features.saturation < 0.35 and (features.contrast > 0.4 or features.brightness < 0.4):
        style_tags.append("高级感")
        mood.append("克制")
    # 科技感：冷色 + 高对比
    if not features.warm and features.contrast > 0.35:
        style_tags.append("科技感")
        mood.append("理性")
    # 温暖感：暖色 + 中高亮度
    if features.warm and features.brightness > 0.5:
        style_tags.append("温暖感")
        mood.append("亲和")
    # 年轻化：高饱和 + 高亮度
    if features.saturation > 0.5 and features.brightness > 0.55:
        style_tags.append("年轻化")
        mood.append("活力")
    # 极简：主色少 + 低饱和
    if len(features.palette) <= 3 and features.saturation < 0.4:
        style_tags.append("极简")
        mood.append("干净")

    if not style_tags:
        style_tags.append("均衡")
        mood.append("稳定")

    # 品牌定位
    if "高级感" in style_tags:
        brand = "高端 / 品质定位"
    elif "科技感" in style_tags:
        brand = "创新 / 科技定位"
    elif "年轻化" in style_tags:
        brand = "潮流 / 年轻客群"
    else:
        brand = "大众 / 通用定位"

    # 冷暖情绪补充
    mood.append("暖调" if features.warm else "冷调")

    return VisualStyle(
        style_tags=style_tags,
        mood_keywords=list(dict.fromkeys(mood)),
        brand_position=brand,
    )
