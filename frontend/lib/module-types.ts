// 规范排版模块类型（与后端 layout_blueprint.MODULE_TYPE_ORDER 一致）。
// 校正台用它做下拉选择，避免手打枚举字符串导致的错拼与校验失败。

export const MODULE_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "main_title", label: "主标题" },
  { value: "subtitle", label: "副标题" },
  { value: "body_text", label: "正文" },
  { value: "product_image", label: "产品主图" },
  { value: "person_image", label: "人物图" },
  { value: "scene_image", label: "场景图" },
  { value: "selling_point", label: "卖点" },
  { value: "feature_list", label: "功能清单" },
  { value: "parameter_table", label: "参数表" },
  { value: "price", label: "价格" },
  { value: "logo", label: "Logo" },
  { value: "cta", label: "行动引导" },
  { value: "footnote", label: "脚注" },
  { value: "decoration", label: "装饰" },
  { value: "background", label: "背景" },
  { value: "other", label: "其他" },
];

const LABEL_BY_VALUE = new Map(
  MODULE_TYPE_OPTIONS.map((option) => [option.value, option.label])
);

export function moduleTypeLabel(value: string): string {
  return LABEL_BY_VALUE.get(value) || value;
}
