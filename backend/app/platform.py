"""媒介 / 平台类型识别，用于让绘图提示词贴合原图的平台风格。

避免所有图都套用"电商产品级 8k"话术：UI 界面就用界面设计语言，
海报用平面设计语言，网页用网页设计语言……与被拆解图片的平台类型一致。
"""
from __future__ import annotations

# 各平台的提示词框架（zh/en）与质量后缀（quality），刻意区分开电商话术
PLATFORM_STYLES: dict[str, dict] = {
    "ui": {
        "label": "UI / 界面",
        "zh": "UI 界面设计, 数字产品界面, 现代扁平, 栅格对齐, 清晰规整",
        "en": "UI design, digital product interface, clean modern flat design, aligned grid",
        "quality": "高保真, 像素级精致, 符合设计规范",
    },
    "web": {
        "label": "网页 / 官网",
        "zh": "网页设计, 官网首屏, 响应式布局, 现代 Web 视觉",
        "en": "web design, website hero section, responsive layout, modern web visual",
        "quality": "高保真, 精致排版",
    },
    "poster": {
        "label": "海报 / KV",
        "zh": "平面海报设计, 主视觉 KV, 强排版张力",
        "en": "graphic poster design, key visual, strong typographic layout",
        "quality": "高质量, 印刷级精细",
    },
    "banner": {
        "label": "Banner / 运营",
        "zh": "运营 Banner, 横版主视觉, 平面设计",
        "en": "marketing banner, hero banner visual, graphic design",
        "quality": "高质量, 商业级",
    },
    "ecommerce": {
        "label": "电商 / 产品",
        "zh": "电商产品主图, 商品视觉, 质感刻画",
        "en": "e-commerce product hero shot, commercial product visual",
        "quality": "商业摄影级, 8k, 精致细节",
    },
    "social": {
        "label": "社媒 / 内容",
        "zh": "社交媒体配图, 内容运营视觉",
        "en": "social media graphic, content visual",
        "quality": "高质量, 干净精致",
    },
    "illustration": {
        "label": "插画 / 图形",
        "zh": "插画设计, 矢量图形化表达",
        "en": "illustration design, vector graphic",
        "quality": "精致插画, 风格统一",
    },
    "brand": {
        "label": "品牌 / VI",
        "zh": "品牌视觉, VI 应用, 系统化设计",
        "en": "brand identity visual, VI application, systematic design",
        "quality": "高质量, 系统统一",
    },
    "generic": {
        "label": "视觉设计",
        "zh": "视觉设计",
        "en": "visual design",
        "quality": "高质量, 精致细节",
    },
}

# 关键词 -> 平台 key（顺序敏感，先具体后宽泛）
_KEYWORDS = [
    ("ui", ["ui", "界面", "原型", "app", "dashboard", "控制台", "后台", "组件", "交互"]),
    ("web", ["网页", "官网", "web", "landing", "首屏", "落地页", "网站"]),
    ("ecommerce", ["电商", "产品图", "商品", "详情页", "带货", "主图", "sku"]),
    ("poster", ["海报", "kv", "主视觉", "poster", "招贴"]),
    ("banner", ["banner", "横幅", "通栏", "横版主视觉"]),
    ("social", ["社媒", "朋友圈", "信息流", "小红书", "公众号", "封面", "内容图", "配图"]),
    ("illustration", ["插画", "图形", "矢量", "illustration", "icon", "图标"]),
    ("brand", ["品牌", "vi", "logo", "标识"]),
]


def infer_platform(image_type: str = "", orientation: str = "", extra: str = "") -> str:
    """从图片类型/场景描述推断平台 key；识别不出时按画幅回退（避免默认电商）。"""
    s = f"{image_type} {extra}".lower()
    for key, kws in _KEYWORDS:
        if any(k in s for k in kws):
            return key
    if orientation == "portrait":
        return "poster"
    if orientation == "landscape":
        return "banner"
    if orientation == "square":
        return "social"
    return "generic"


def style_of(image_type: str = "", orientation: str = "", extra: str = "") -> dict:
    return PLATFORM_STYLES[infer_platform(image_type, orientation, extra)]
