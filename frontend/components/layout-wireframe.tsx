"use client";

import { PointerEvent, useRef } from "react";
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
  backgroundImageUrl = "",
  onBackgroundImageError,
  onModuleChange,
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
  backgroundImageUrl?: string;
  onBackgroundImageError?: () => void;
  onModuleChange?: (index: number, patch: Partial<LayoutModule>) => void;
}) {
  const [ratioWidth, ratioHeight] = blueprint.canvas_ratio
    .split(":")
    .map((value) => Number(value) || 1);
  const stroke = accent === "red" ? "#ff5159" : "#20242c";
  const canvasRef = useRef<HTMLDivElement>(null);
  const moduleStroke = (type: string) =>
    type === "product_image"
      ? "#2563eb"
      : ["main_title", "subtitle", "body_text", "selling_point", "feature_list", "parameter_table", "price", "cta", "footnote"].includes(type)
        ? "#16a34a"
        : stroke;
  const beginMove = (
    event: PointerEvent<HTMLElement>,
    index: number,
    module: LayoutModule,
    mode: "move" | "resize",
  ) => {
    if (!onModuleChange || !canvasRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const rect = canvasRef.current.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const target = event.currentTarget;
    const move = (next: globalThis.PointerEvent) => {
      const dx = (next.clientX - startX) / rect.width;
      const dy = (next.clientY - startY) / rect.height;
      if (mode === "move") {
        onModuleChange(index, {
          x: Math.max(0, Math.min(1 - module.width, module.x + dx)),
          y: Math.max(0, Math.min(1 - module.height, module.y + dy)),
        });
      } else {
        onModuleChange(index, {
          width: Math.max(0.02, Math.min(1 - module.x, module.width + dx)),
          height: Math.max(0.02, Math.min(1 - module.y, module.height + dy)),
        });
      }
    };
    const end = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", end);
      target.removeEventListener("pointercancel", end);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", end);
    target.addEventListener("pointercancel", end);
  };

  return (
    <div
      ref={canvasRef}
      className={`relative mx-auto w-full overflow-hidden rounded-sm border border-gray-200 bg-white shadow-sm ${className}`}
      style={{
        aspectRatio: `${ratioWidth}/${ratioHeight}`,
      }}
      aria-label="排版低保真框架图"
    >
      {backgroundImageUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={backgroundImageUrl}
          alt="案例原始成品图"
          className="pointer-events-none absolute inset-0 h-full w-full object-contain"
          onError={onBackgroundImageError}
        />
      )}
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
      {blueprint.modules_json.map((module, index) => (
        <div
          key={module.id}
          className={`absolute overflow-hidden bg-transparent ${onModuleChange ? "cursor-move touch-none" : ""}`}
          onPointerDown={(event) => beginMove(event, index, module, "move")}
          style={{
            left: `${bounded(module.x) * 100}%`,
            top: `${bounded(module.y) * 100}%`,
            width: `${bounded(module.width) * 100}%`,
            height: `${bounded(module.height) * 100}%`,
            border: `2px solid ${moduleStroke(module.type)}`,
            borderRadius: "3px",
          }}
          title={`${module.priority}. ${module.description || module.type}`}
        >
          {showLabels && (
            <span
              className="absolute left-1 top-0.5 max-w-[calc(100%-8px)] truncate bg-white/90 px-1 text-[9px] font-medium leading-4"
              style={{ color: moduleStroke(module.type) }}
            >
              {module.priority}. {moduleLabels[module.type] || module.description || module.type}
            </span>
          )}
          {onModuleChange && (
            <span
              aria-label="调整区域大小"
              className="absolute bottom-0 right-0 h-3 w-3 cursor-se-resize border-l border-t border-white bg-current"
              style={{ color: moduleStroke(module.type) }}
              onPointerDown={(event) => beginMove(event, index, module, "resize")}
            />
          )}
        </div>
      ))}
    </div>
  );
}
