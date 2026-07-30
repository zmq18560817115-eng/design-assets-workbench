"use client";

import {
  LayoutBlueprintInput,
  LayoutModule,
  LayoutPattern,
  NormalizedRegion,
} from "@/lib/api";

const moduleLabels: Record<string, string> = {
  main_title: "主标题",
  title: "标题",
  subtitle: "副标题",
  product_image: "主视觉",
  supporting_image: "辅助图",
  supporting_text: "信息",
  body: "正文",
  data: "数据",
  cta: "引导",
  footer: "页脚",
  body_text: "正文",
  person_image: "人物图",
  scene_image: "场景图",
  selling_point: "卖点",
  feature_list: "功能列表",
  parameter_table: "参数表",
  price: "价格",
  logo: "标识",
  footnote: "脚注",
  decoration: "装饰",
  background: "背景",
  other: "其他",
};

function bounded(value: number) {
  return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
}

export function LayoutWireframe({
  blueprint,
  showLabels = false,
  showFocalRegion = false,
  accent = "red",
  className = "",
}: {
  blueprint:
    | LayoutBlueprintInput
    | LayoutPattern
    | {
        canvas_ratio: string;
        focal_region?: NormalizedRegion | null;
        modules_json: LayoutModule[];
      };
  showLabels?: boolean;
  showFocalRegion?: boolean;
  accent?: "red" | "black";
  className?: string;
}) {
  const [ratioWidth, ratioHeight] = blueprint.canvas_ratio
    .split(":")
    .map((value) => Number(value) || 1);
  const stroke = accent === "red" ? "#ff5159" : "#20242c";

  return (
    <div
      className={`relative mx-auto w-full overflow-hidden rounded-sm border border-gray-200 bg-white shadow-sm ${className}`}
      style={{ aspectRatio: `${ratioWidth}/${ratioHeight}` }}
      aria-label="排版低保真框架图"
    >
      {showFocalRegion && blueprint.focal_region && (
        <div
          className="pointer-events-none absolute border border-dashed border-violet-400"
          style={{
            left: `${bounded(blueprint.focal_region.x) * 100}%`,
            top: `${bounded(blueprint.focal_region.y) * 100}%`,
            width: `${bounded(blueprint.focal_region.width) * 100}%`,
            height: `${bounded(blueprint.focal_region.height) * 100}%`,
          }}
        />
      )}
      {blueprint.modules_json.map((module) => (
        <div
          key={module.id}
          className="absolute overflow-hidden bg-transparent"
          style={{
            left: `${bounded(module.x) * 100}%`,
            top: `${bounded(module.y) * 100}%`,
            width: `${bounded(module.width) * 100}%`,
            height: `${bounded(module.height) * 100}%`,
            border: `2px solid ${stroke}`,
            borderRadius: "3px",
          }}
          title={`${module.priority}. ${module.description || module.type}`}
        >
          {showLabels && (
            <span
              className="absolute left-1 top-0.5 max-w-[calc(100%-8px)] truncate bg-white/90 px-1 text-[9px] font-medium leading-4"
              style={{ color: stroke }}
            >
              {module.priority}. {moduleLabels[module.type] || module.description || module.type}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
