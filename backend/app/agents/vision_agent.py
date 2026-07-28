"""Vision Agent —— 识别图片内容、场景、对象。

对应技术方案「五、AI Agent流程 1. Vision Agent」。
基于底层视觉特征，推断图片类型、行业与使用场景。
"""
from __future__ import annotations

from ..schemas import CaseBasics
from ..vision_provider import ImageFeatures


def run(features: ImageFeatures) -> CaseBasics:
    # 根据宽高比推断图片类型
    if features.orientation == "portrait":
        image_type = "海报 / 竖版视觉"
        scene = "社媒宣发、活动海报"
    elif features.orientation == "landscape":
        image_type = "Banner / 横版主视觉"
        scene = "官网首屏、活动 Banner"
    else:
        image_type = "方图 / 卡片视觉"
        scene = "社媒配图、信息流"

    # 根据色彩与亮度粗略推断行业倾向
    names = set(features.color_names)
    if features.brightness > 0.7 and features.saturation < 0.35:
        industry = "美妆 / 生活方式"
    elif "蓝" in names or "青" in names:
        industry = "科技 / 互联网"
    elif features.warm and features.saturation > 0.4:
        industry = "餐饮 / 消费品"
    elif features.brightness < 0.35:
        industry = "潮流 / 奢侈品"
    else:
        industry = "泛品牌 / 通用"

    return CaseBasics(image_type=image_type, industry=industry, scene=scene)
