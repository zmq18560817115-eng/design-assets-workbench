"""Material-library categories and category-specific analysis guidance."""

ASSET_CATEGORIES = {
    "layout": {
        "label": "排版",
        "focus": "重点拆解网格、模块、信息层级、对齐、留白、间距、图文比例和阅读动线。",
    },
    "style": {
        "label": "风格",
        "focus": "重点拆解视觉语言、形式特征、情绪、品牌调性、字体气质、图形与材质表现。",
    },
    "color": {
        "label": "色彩",
        "focus": "重点拆解主色、辅色、点缀色、面积比例、明度与饱和度、对比关系和适用场景。",
    },
    "photo": {
        "label": "实拍图",
        "focus": "重点拆解主体、构图、景别、机位、光线、背景、场景、产品摆放、材质和标题压字空间。",
    },
}


def normalize_category(value: str) -> str:
    return value if value in ASSET_CATEGORIES else "layout"


def category_label(value: str) -> str:
    return ASSET_CATEGORIES[normalize_category(value)]["label"]


def category_focus(value: str) -> str:
    return ASSET_CATEGORIES[normalize_category(value)]["focus"]
