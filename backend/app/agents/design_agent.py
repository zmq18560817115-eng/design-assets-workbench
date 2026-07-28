"""Design Agent —— 拆解色彩、构图、光影、材质、排版。

对应技术方案「五、AI Agent流程 3. Design Agent」。
"""
from __future__ import annotations

from ..schemas import ColorSystem, Composition, Light
from ..vision_provider import ImageFeatures


def run(features: ImageFeatures) -> tuple[ColorSystem, Composition, Light, str]:
    # 色彩体系
    tone = "暖色调" if features.warm else "冷色调"
    sat_desc = "高饱和" if features.saturation > 0.5 else ("低饱和" if features.saturation < 0.3 else "中饱和")
    color = ColorSystem(
        palette=features.palette,
        primary=features.primary_hex,
        description=f"{tone}为主，{sat_desc}，主色 {features.primary_hex}，"
        f"色板以 {'、'.join(features.color_names[:3]) or '中性色'} 为核心。",
    )

    # 构图（由宽高比 + 对比度推断）
    if features.orientation == "portrait":
        comp_type = "竖向引导 / 上下分区"
    elif features.orientation == "landscape":
        comp_type = "横向延展 / 左右分区"
    else:
        comp_type = "居中聚焦 / 对称"
    comp_desc = (
        f"画面比例 {features.aspect_ratio}，"
        + ("对比强烈、主体突出。" if features.contrast > 0.45 else "层次柔和、留白充分。")
    )
    composition = Composition(type=comp_type, description=comp_desc)

    # 光影
    if features.brightness > 0.7:
        light_type = "高调 / 明亮通透"
    elif features.brightness < 0.35:
        light_type = "低调 / 暗部氛围"
    else:
        light_type = "中间调 / 自然光"
    light_desc = (
        f"整体亮度 {features.brightness}，"
        + ("明暗反差大，立体感强。" if features.contrast > 0.45 else "光线均匀，质感平和。")
    )
    light = Light(type=light_type, description=light_desc)

    # 材质表现
    if features.saturation < 0.3 and features.brightness > 0.6:
        material = "哑光 / 磨砂质感，干净通透"
    elif features.contrast > 0.5:
        material = "光泽 / 金属或玻璃反光质感"
    else:
        material = "自然材质，质感真实"

    return color, composition, light, material
