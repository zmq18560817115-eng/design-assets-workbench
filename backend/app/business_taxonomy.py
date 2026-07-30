"""Maintainable exact-alias normalization for business retrieval fields."""
from __future__ import annotations

ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "channel": {
        "小红书": ("小红书", "xhs", "xiaohongshu"),
        "电商详情": ("电商详情", "详情页", "电商长图", "商品详情"),
        "产品海报": ("产品海报", "商品海报"),
        "公众号": ("公众号", "微信公众号", "wechat official account"),
        "官网": ("官网", "官方网站", "brand website"),
    },
    "content_purpose": {
        "参数对比": ("参数对比", "产品对比", "竞品对比"),
        "上新宣传": ("上新", "新品发布", "新品宣传", "上新宣传"),
        "卖点说明": ("卖点说明", "卖点介绍", "产品卖点"),
        "知识科普": ("知识科普", "使用科普", "教育内容"),
        "品牌横幅": ("品牌横幅", "品牌banner", "品牌 banner"),
    },
    "campaign_stage": {
        "上新期": ("上新期", "新品期", "发布期"),
        "日常期": ("日常期", "常规期", "日常投放"),
        "大促期": ("大促期", "促销期", "活动期", "大促"),
        "正式投放": ("正式投放", "投放中", "正式期"),
    },
    "product_category": {
        "吸奶器": ("吸奶器", "吸乳器"),
        "奶瓶": ("奶瓶", "喂养瓶"),
        "纸尿裤": ("纸尿裤", "尿不湿"),
        "辅食机": ("辅食机", "婴儿料理机"),
        "消毒柜": ("消毒柜", "奶瓶消毒器"),
    },
}


def normalize_business_value(field: str, value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    lookup = raw.casefold()
    if field == "channel" and lookup == "red":
        lookup = "xiaohongshu"
    for canonical, aliases in ALIASES.get(field, {}).items():
        if lookup in {alias.strip().casefold() for alias in aliases}:
            return canonical
    return raw


def values_match(field: str, left: str, right: str) -> bool:
    a = normalize_business_value(field, left)
    b = normalize_business_value(field, right)
    return bool(a and b and a.casefold() == b.casefold())
