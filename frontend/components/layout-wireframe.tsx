"use client";

import { useRef } from "react";
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

function round(value: number) {
  return Math.round(value * 1000) / 1000;
}

type DragState = {
  index: number;
  mode: "move" | "resize";
  startX: number;
  startY: number;
  orig: { x: number; y: number; width: number; height: number };
};

export function LayoutWireframe({
  blueprint,
  showLabels = false,
  showFocalRegion = false,
  accent = "red",
  className = "",
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
  // 提供后进入可编辑模式：拖动模块移动、拖右下角缩放。
  onModuleChange?: (index: number, patch: Partial<LayoutModule>) => void;
}) {
  const [ratioWidth, ratioHeight] = blueprint.canvas_ratio
    .split(":")
    .map((value) => Number(value) || 1);
  const stroke = accent === "red" ? "#ff5159" : "#20242c";
  const editable = Boolean(onModuleChange);

  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  const beginDrag = (
    event: React.PointerEvent,
    index: number,
    mode: "move" | "resize"
  ) => {
    if (!onModuleChange) return;
    event.preventDefault();
    event.stopPropagation();
    const target = blueprint.modules_json[index];
    dragRef.current = {
      index,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      orig: {
        x: target.x,
        y: target.y,
        width: target.width,
        height: target.height,
      },
    };
    containerRef.current?.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent) => {
    const drag = dragRef.current;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!drag || !rect || !onModuleChange) return;
    const dx = (event.clientX - drag.startX) / rect.width;
    const dy = (event.clientY - drag.startY) / rect.height;
    if (drag.mode === "move") {
      const x = Math.max(0, Math.min(1 - drag.orig.width, drag.orig.x + dx));
      const y = Math.max(0, Math.min(1 - drag.orig.height, drag.orig.y + dy));
      onModuleChange(drag.index, { x: round(x), y: round(y) });
    } else {
      const width = Math.max(0.02, Math.min(1 - drag.orig.x, drag.orig.width + dx));
      const height = Math.max(0.02, Math.min(1 - drag.orig.y, drag.orig.height + dy));
      onModuleChange(drag.index, { width: round(width), height: round(height) });
    }
  };

  const endDrag = (event: React.PointerEvent) => {
    if (dragRef.current) {
      containerRef.current?.releasePointerCapture(event.pointerId);
      dragRef.current = null;
    }
  };

  return (
    <div
      ref={containerRef}
      className={`relative mx-auto w-full overflow-hidden rounded-sm border border-gray-200 bg-white shadow-sm ${className}`}
      style={{ aspectRatio: `${ratioWidth}/${ratioHeight}` }}
      aria-label="排版低保真框架图"
      onPointerMove={editable ? handlePointerMove : undefined}
      onPointerUp={editable ? endDrag : undefined}
      onPointerCancel={editable ? endDrag : undefined}
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
      {blueprint.modules_json.map((module, index) => (
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
            cursor: editable ? "move" : undefined,
            touchAction: editable ? "none" : undefined,
          }}
          title={`${module.priority}. ${module.description || module.type}`}
          onPointerDown={
            editable ? (event) => beginDrag(event, index, "move") : undefined
          }
        >
          {showLabels && (
            <span
              className="pointer-events-none absolute left-1 top-0.5 max-w-[calc(100%-8px)] truncate bg-white/90 px-1 text-[9px] font-medium leading-4"
              style={{ color: stroke }}
            >
              {module.priority}. {moduleLabels[module.type] || module.description || module.type}
            </span>
          )}
          {editable && (
            <span
              role="button"
              aria-label="缩放模块"
              className="absolute bottom-0 right-0 h-3 w-3"
              style={{
                cursor: "nwse-resize",
                background: stroke,
                borderTopLeftRadius: "3px",
                touchAction: "none",
              }}
              onPointerDown={(event) => beginDrag(event, index, "resize")}
            />
          )}
        </div>
      ))}
    </div>
  );
}
