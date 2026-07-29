"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  ServiceRunDetail,
  ServiceRunSummary,
} from "@/lib/api";

const statusLabels: Record<string, string> = {
  generated: "待反馈",
  adopted: "已采用",
  rejected: "不采用",
  needs_revision: "需调整",
};

const statusStyles: Record<string, string> = {
  generated: "bg-gray-100 text-gray-500",
  adopted: "bg-emerald-50 text-emerald-600",
  rejected: "bg-red-50 text-red-500",
  needs_revision: "bg-amber-50 text-amber-600",
};

export default function ServiceHistoryPage() {
  const [runs, setRuns] = useState<ServiceRunSummary[]>([]);
  const [selected, setSelected] = useState<ServiceRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api
      .serviceRuns()
      .then((items) => {
        setRuns(items);
        if (items[0]) {
          setDetailLoading(true);
          api
            .serviceRun(items[0].id)
            .then(setSelected)
            .finally(() => setDetailLoading(false));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const openRun = (id: number) => {
    setDetailLoading(true);
    api
      .serviceRun(id)
      .then(setSelected)
      .finally(() => setDetailLoading(false));
  };

  return (
    <div className="space-y-7">
      <section className="rounded-[28px] border border-line bg-white p-6 md:p-8">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
              Service operations
            </div>
            <h1 className="mt-2 text-3xl font-semibold">业务视觉服务记录</h1>
            <p className="mt-2 text-sm text-gray-500">
              复盘需求、公司证据、生成方向和最终业务结果。
            </p>
          </div>
          <Link
            href="/service"
            className="rounded-xl bg-ink px-5 py-3 text-sm text-white"
          >
            新建业务方向
          </Link>
        </div>
      </section>

      {loading ? (
        <div className="py-20 text-center text-gray-400">正在读取服务记录…</div>
      ) : runs.length === 0 ? (
        <section className="rounded-3xl border border-dashed border-line bg-white p-16 text-center">
          <h2 className="text-lg font-semibold">还没有真实业务产出记录</h2>
          <p className="mt-2 text-sm text-gray-500">
            完成一次业务视觉生成后，需求、提示词和采用结果会出现在这里。
          </p>
          <Link
            href="/service"
            className="mt-5 inline-flex rounded-xl bg-accent px-5 py-3 text-sm text-white"
          >
            创建第一条服务记录
          </Link>
        </section>
      ) : (
        <section className="grid gap-5 xl:grid-cols-[360px_1fr]">
          <aside className="space-y-3">
            {runs.map((run) => (
              <button
                key={run.id}
                onClick={() => openRun(run.id)}
                className={`w-full rounded-2xl border bg-white p-4 text-left transition ${
                  selected?.id === run.id
                    ? "border-accent ring-2 ring-accent/10"
                    : "border-line hover:border-accent/40"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs text-gray-400">#{run.id}</span>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[10px] ${
                      statusStyles[run.status] || statusStyles.generated
                    }`}
                  >
                    {statusLabels[run.status] || run.status}
                  </span>
                </div>
                <div className="mt-2 line-clamp-2 text-sm font-medium leading-6">
                  {run.request_text || "仅使用意向图生成"}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-gray-400">
                  {run.industry && <span>{run.industry}</span>}
                  {run.channel && <span>· {run.channel}</span>}
                  {run.campaign_stage && <span>· {run.campaign_stage}</span>}
                </div>
                <div className="mt-2 text-[10px] text-gray-400">
                  {new Date(run.created_at).toLocaleString("zh-CN")}
                </div>
              </button>
            ))}
          </aside>

          <div className="min-h-[520px] rounded-3xl border border-line bg-white p-6 md:p-8">
            {detailLoading || !selected ? (
              <div className="py-20 text-center text-gray-400">正在加载详情…</div>
            ) : (
              <div className="space-y-7">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-xs text-gray-400">
                      服务记录 #{selected.id}
                    </div>
                    <h2 className="mt-2 text-2xl font-semibold">
                      {selected.industry || "未指定业务线"} ·{" "}
                      {selected.channel || "未指定渠道"}
                    </h2>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1.5 text-xs ${
                      statusStyles[selected.status] || statusStyles.generated
                    }`}
                  >
                    {statusLabels[selected.status] || selected.status}
                  </span>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  {[
                    ["营销阶段", selected.campaign_stage || "未填写"],
                    ["业务目标", selected.business_goal || "未填写"],
                    [
                      "公司证据",
                      `${selected.evidence_case_ids.length} 个引用案例`,
                    ],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-2xl bg-canvas p-4">
                      <div className="text-xs text-gray-400">{label}</div>
                      <div className="mt-2 text-sm font-medium">{value}</div>
                    </div>
                  ))}
                </div>

                <div>
                  <h3 className="text-sm font-semibold">原始业务需求</h3>
                  <p className="mt-2 rounded-2xl bg-canvas p-4 text-sm leading-7 text-gray-600">
                    {selected.request_text || "仅使用意向图生成"}
                  </p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold">推荐视觉方向</h3>
                  <div className="mt-3 grid gap-2">
                    {(selected.result.directions || []).map((direction, index) => (
                      <div
                        key={`${direction}-${index}`}
                        className="rounded-2xl border border-line p-4 text-sm leading-7 text-gray-600"
                      >
                        <span className="mr-2 font-semibold text-accent">
                          0{index + 1}
                        </span>
                        {direction}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl bg-ink p-5 text-white">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold">白板生图提示词</h3>
                    <button
                      onClick={() =>
                        navigator.clipboard.writeText(selected.result.prompt || "")
                      }
                      className="rounded-lg bg-white px-3 py-1.5 text-xs text-ink"
                    >
                      复制
                    </button>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-xs leading-6 text-white/70">
                    {selected.result.prompt || "暂无提示词"}
                  </p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold">业务反馈</h3>
                  <div className="mt-2 rounded-2xl border border-line p-4 text-sm text-gray-600">
                    {selected.feedback
                      ? `${selected.actor || "未署名"}：${selected.feedback}`
                      : "尚未记录最终业务结果，请回到生成页完成采用、调整或淘汰反馈。"}
                  </div>
                </div>

                {selected.evidence_case_ids.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold">引用的公司证据</h3>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selected.evidence_case_ids.map((id) => (
                        <Link
                          key={id}
                          href={`/cases/${id}`}
                          className="rounded-full bg-lilac px-3 py-1.5 text-xs text-accent"
                        >
                          案例 #{id}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
