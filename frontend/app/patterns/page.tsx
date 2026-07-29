"use client";

import { useEffect, useState } from "react";
import { api, LayoutPattern } from "@/lib/api";
import { LayoutWireframe } from "@/components/layout-wireframe";
import { Card, Tag } from "@/components/ui";

export default function LayoutPatternsPage() {
  const [items, setItems] = useState<LayoutPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [orientation, setOrientation] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .layoutPatterns({
        orientation,
        review_status: reviewStatus,
      })
      .then(setItems)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "读取排版模式失败")
      )
      .finally(() => setLoading(false));
  }, [orientation, reviewStatus]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            Layout patterns
          </div>
          <h1 className="mt-2 text-3xl font-bold">排版模式库</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500">
            从人工确认的案例骨架中沉淀可复用结构。每个模式保留来源案例、适用场景和版本。
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={orientation}
            onChange={(event) => setOrientation(event.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
          >
            <option value="">全部方向</option>
            <option value="portrait">竖版</option>
            <option value="landscape">横版</option>
            <option value="square">方形</option>
          </select>
          <select
            value={reviewStatus}
            onChange={(event) => setReviewStatus(event.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
          >
            <option value="">全部状态</option>
            <option value="human_edited">待确认</option>
            <option value="verified">已确认</option>
          </select>
        </div>
      </div>

      {loading && <p className="mt-8 text-sm text-gray-500">正在读取模式库…</p>}
      {error && <p className="mt-8 text-sm text-rose-500">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <Card className="mt-8 text-sm text-gray-500">
          暂无匹配模式。请先在案例详情中确认排版骨架，再沉淀为模式。
        </Card>
      )}

      <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Card key={item.id} className="flex flex-col">
            <div className="rounded-xl bg-gray-50 p-4">
              <LayoutWireframe
                blueprint={item}
                showLabels={false}
                className="max-h-[310px] max-w-[300px]"
              />
            </div>
            <div className="mt-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">{item.name}</h2>
                <p className="mt-1 text-xs leading-5 text-gray-500">
                  {item.description || item.usage_notes || "暂无说明"}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-1 text-[10px] ${
                  item.review_status === "verified"
                    ? "bg-emerald-50 text-emerald-600"
                    : "bg-amber-50 text-amber-600"
                }`}
              >
                {item.review_status === "verified" ? "已确认" : "待确认"}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {[...item.scene_tags, ...item.channel_tags].map((tag) => (
                <Tag key={`${item.id}-${tag}`}>{tag}</Tag>
              ))}
            </div>
            <div className="mt-auto pt-4 text-[11px] text-gray-400">
              v{item.version} · {item.orientation} · {item.module_count} 个模块 ·
              来源案例 {item.source_case_ids.join("、")}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
