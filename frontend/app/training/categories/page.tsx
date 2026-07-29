"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, CategoryDiscovery } from "@/lib/api";

const categories = ["layout", "style", "color", "photo"] as const;
const categoryLabels = {
  layout: "排版",
  style: "风格",
  color: "色彩",
  photo: "实拍图",
};

type Candidate =
  CategoryDiscovery["candidates"][keyof CategoryDiscovery["candidates"]][number] & {
    business_line: string;
  };

export default function CategoryReviewPage() {
  const [data, setData] = useState<CategoryDiscovery[]>([]);
  const [businessLine, setBusinessLine] = useState("");
  const [suggestedCategory, setSuggestedCategory] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const load = () =>
    api
      .categoryDiscovery()
      .then(setData)
      .finally(() => setLoading(false));

  useEffect(() => {
    setReviewer(window.localStorage.getItem("category-reviewer") || "");
    load().catch(() => setMessage("分类候选加载失败，请确认后端服务。"));
  }, []);

  const allCandidates = useMemo(
    () =>
      data.flatMap((line) =>
        categories.flatMap((category) =>
          line.candidates[category].map((candidate) => ({
            ...candidate,
            business_line: line.business_line,
          }))
        )
      ),
    [data]
  );

  const queue = useMemo(
    () =>
      allCandidates.filter(
        (candidate) =>
          candidate.status === "pending" &&
          (!businessLine || candidate.business_line === businessLine) &&
          (!suggestedCategory ||
            candidate.suggested_category === suggestedCategory)
      ),
    [allCandidates, businessLine, suggestedCategory]
  );

  useEffect(() => {
    setIndex(0);
  }, [businessLine, suggestedCategory]);

  useEffect(() => {
    if (queue.length && index >= queue.length) {
      setIndex(queue.length - 1);
    }
  }, [queue.length, index]);

  const candidate: Candidate | undefined = queue[index];
  const reviewed = allCandidates.filter(
    (item) => item.status === "accepted" || item.status === "overridden"
  ).length;

  const classify = async (
    category: "layout" | "style" | "color" | "photo"
  ) => {
    if (!candidate) return;
    if (!reviewer.trim()) {
      setMessage("请先填写审核人姓名或岗位。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      window.localStorage.setItem("category-reviewer", reviewer.trim());
      await api.batchCategorize([candidate.case_id], category, reviewer.trim());
      const decision =
        category === candidate.suggested_category ? "采纳模型建议" : "人工覆盖";
      setMessage(
        `案例 #${candidate.case_id} 已归入${categoryLabels[category]}（${decision}）。`
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "归类保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[30px] bg-ink px-6 py-8 text-white md:px-9">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-white/45">
              Human-in-the-loop classification
            </div>
            <h1 className="mt-3 text-3xl font-semibold">公司素材分类审核台</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/60">
              对照原图确认主要学习目标。模型建议只用于辅助判断，人工选择才会写入正式素材仓库。
            </p>
          </div>
          <Link
            href="/training"
            className="rounded-xl border border-white/15 px-4 py-2.5 text-sm"
          >
            返回训练工作台
          </Link>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-line bg-white p-5">
          <div className="text-xs text-gray-400">候选总数</div>
          <div className="mt-2 text-3xl font-semibold">{allCandidates.length}</div>
        </div>
        <div className="rounded-2xl border border-line bg-white p-5">
          <div className="text-xs text-gray-400">已人工处理</div>
          <div className="mt-2 text-3xl font-semibold text-emerald-600">
            {reviewed}
          </div>
        </div>
        <div className="rounded-2xl border border-line bg-white p-5">
          <div className="text-xs text-gray-400">当前筛选待处理</div>
          <div className="mt-2 text-3xl font-semibold text-amber-600">
            {queue.length}
          </div>
        </div>
      </section>

      <section className="grid gap-3 rounded-2xl border border-line bg-white p-4 md:grid-cols-3">
        <select
          value={businessLine}
          onChange={(event) => setBusinessLine(event.target.value)}
          className="rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm"
        >
          <option value="">全部业务线</option>
          {data.map((line) => (
            <option key={line.business_line} value={line.business_line}>
              {line.business_line}
            </option>
          ))}
        </select>
        <select
          value={suggestedCategory}
          onChange={(event) => setSuggestedCategory(event.target.value)}
          className="rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm"
        >
          <option value="">全部模型建议</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              建议：{categoryLabels[category]}
            </option>
          ))}
        </select>
        <input
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          placeholder="审核人姓名或岗位 *"
          className="rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
        />
      </section>

      {loading ? (
        <div className="py-20 text-center text-gray-400">正在加载分类候选…</div>
      ) : !candidate ? (
        <div className="rounded-3xl border border-emerald-200 bg-emerald-50 py-20 text-center">
          <div className="text-xl font-semibold text-emerald-700">
            当前筛选下没有待处理候选
          </div>
          <div className="mt-2 text-sm text-emerald-600">
            可以切换业务线或模型建议类别继续审核。
          </div>
        </div>
      ) : (
        <section className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
          <div className="overflow-hidden rounded-3xl border border-line bg-white">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={candidate.image_url}
              alt={candidate.case_name}
              className="max-h-[72vh] w-full bg-gray-100 object-contain"
            />
          </div>
          <aside className="h-fit rounded-3xl border border-line bg-white p-6 lg:sticky lg:top-24">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span>
                {index + 1}/{queue.length}
              </span>
              <span>{candidate.business_line}</span>
            </div>
            <h2 className="mt-3 text-lg font-semibold">
              #{candidate.case_id} · {candidate.case_name}
            </h2>
            <div className="mt-4 rounded-2xl bg-blue-50 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-blue-800">
                  模型建议：{categoryLabels[candidate.suggested_category]}
                </span>
                <span className="text-sm text-blue-600">
                  {candidate.confidence}%
                </span>
              </div>
              <p className="mt-2 text-xs leading-6 text-blue-700">
                {candidate.reason}
              </p>
              <ul className="mt-2 space-y-1 text-[11px] leading-5 text-blue-600">
                {candidate.signals.map((signal) => (
                  <li key={signal}>· {signal}</li>
                ))}
              </ul>
            </div>
            <div className="mt-4 text-xs text-gray-500">
              当前正式类别：
              {categoryLabels[
                candidate.current_category as keyof typeof categoryLabels
              ] || candidate.current_category}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              {categories.map((category) => (
                <button
                  key={category}
                  disabled={saving}
                  onClick={() => classify(category)}
                  className={`rounded-xl px-3 py-3 text-sm disabled:opacity-50 ${
                    category === candidate.suggested_category
                      ? "bg-accent text-white"
                      : "border border-line bg-white hover:border-accent"
                  }`}
                >
                  {category === candidate.suggested_category
                    ? `采纳：${categoryLabels[category]}`
                    : `改为：${categoryLabels[category]}`}
                </button>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setIndex((value) => Math.max(0, value - 1))}
                disabled={index === 0}
                className="flex-1 rounded-xl border border-line px-3 py-2 text-sm disabled:opacity-40"
              >
                上一张
              </button>
              <button
                onClick={() =>
                  setIndex((value) => Math.min(queue.length - 1, value + 1))
                }
                disabled={index >= queue.length - 1}
                className="flex-1 rounded-xl border border-line px-3 py-2 text-sm disabled:opacity-40"
              >
                跳过 / 下一张
              </button>
            </div>
            {message && (
              <div className="mt-4 rounded-xl bg-canvas p-3 text-xs text-gray-600">
                {message}
              </div>
            )}
          </aside>
        </section>
      )}
    </div>
  );
}
