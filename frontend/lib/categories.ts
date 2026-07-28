export const ASSET_CATEGORIES = [
  {
    value: "layout",
    label: "排版",
    note: "网格 · 层级 · 留白 · 阅读动线",
    subcategories: ["表格多维对比", "层级分类对比", "选购攻略", "品类对比1V1"],
  },
  {
    value: "style",
    label: "风格",
    note: "视觉语言 · 情绪 · 品牌调性",
    subcategories: [
      "备忘录",
      "常规风格",
      "促销风格",
      "电商风格",
      "海报风格",
      "简约",
      "时间类型",
      "涂鸦手绘风格",
      "网页风格",
    ],
  },
  {
    value: "color",
    label: "色彩",
    note: "主辅色 · 配色比例 · 色彩角色",
    subcategories: ["冷色系", "暖色系", "中性色", "高对比配色", "低饱和配色"],
  },
  {
    value: "photo",
    label: "实拍图",
    note: "构图 · 光线 · 场景 · 材质",
    subcategories: ["背景参考", "标题压字", "产品摆放参考", "内容参考"],
  },
] as const;

export const categoryByValue = (value: string) =>
  ASSET_CATEGORIES.find((item) => item.value === value) || ASSET_CATEGORIES[0];
