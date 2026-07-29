"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, CaseOut, CaseReviewInput } from "@/lib/api";

const categoryLabels: Record<string, string> = {
  layout: "排版",
  style: "风格",
  color: "色彩",
  photo: "实拍图",
};

const splitLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

const splitTags = (value: string) =>
  value
    .split(/[、，,]/)
    .map((item) => item.trim())
    .filter(Boolean);

export default function AnalysisReviewPage() {
  const [items, setItems] = useState<CaseOut[]>([]);
  const [businessLine, setBusinessLine] = useState("");
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [keepReasons, setKeepReasons] = useState("");
  const [avoidReasons, setAvoidReasons] = useState("");
  const [summary, setSummary] = useState("");
  const [layoutType, setLayoutType] = useState("");
  const [styleTags, setStyleTags] = useState("");
  const [colorDescription, setColorDescription] = useState("");

  const load = () =>
    api
      .cases("", "", "", "", undefined, "ai_unverified", "model")
      .then((cases) =>
        setItems(
          cases.filter(
            (item) =>
              item.image?.source_type === "company_published" && item.analysis
          )
        )
      )
      .finally(() => setLoading(false));

  useEffect(() => {
    setReviewer(window.localStorage.getItem("analysis-reviewer") || "");
    load().catch(() => setMessage("模型拆解队列加载失败。"));
  }, []);

  const queue = useMemo(
    () =>
      items.filter(
        (item) => !businessLine || item.business_line === businessLine
      ),
    [items, businessLine]
  );
  const lines = useMemo(
    () =>
      Array.from(
        new Set(items.map((item) => item.business_line).filter(Boolean))
      ),
    [items]
  );
  const item = queue[index];
  const analysis = item?.analysis;

  useEffect(() => {
    setIndex(0);
  }, [businessLine]);

  useEffect(() => {
    if (queue.length && index >= queue.length) {
      setIndex(queue.length - 1);
    }
  }, [queue.length, index]);

  useEffect(() => {
    if (!item || !analysis) return;
    setNotes("");
    setKeepReasons("");
    setAvoidReasons("");
    setSummary(item.summary || "");
    setLayoutType(analysis.layout.layout_type || "");
    setStyleTags((analysis.style.style_tags || []).join("、"));
    setColorDescription(analysis.color.description || "");
    setMessage("");
  }, [item?.id]);

  const review = async (
    trustStatus:
      | "verified"
      | "company_recommended"
      | "rejected",
    decision: "adopt" | "reject"
  ) => {
    if (!item || !analysis) return;
    if (!reviewer.trim()) {
      setMessage("请先填写审核人姓名或岗位。");
      return;
    }
    if (
      trustStatus !== "rejected" &&
      (!splitLines(keepReasons).length || !splitLines(avoidReasons).length)
    ) {
      setMessage("确认或推荐前，必须同时填写延续项和避坑项。");
      return;
    }
    if (
      trustStatus === "rejected" &&
      !splitLines(avoidReasons).length &&
      !notes.trim()
    ) {
      setMessage("淘汰样本前，请填写避坑项或淘汰依据。");
      return;
    }
    setSaving(true);
    setMessage("");
    const payload: CaseReviewInput = {
      reviewer: reviewer.trim(),
      trust_status: trustStatus,
      review_decision: decision,
      review_notes: notes,
      business_line: item.business_line,
      channel: item.channel,
      campaign_stage: item.campaign_stage,
      business_goal: item.business_goal,
      asset_category:
        item.asset_category as CaseReviewInput["asset_category"],
      summary,
      layout_type: layoutType,
      style_tags: splitTags(styleTags),
      color_description: colorDescription,
      keep_reasons: splitLines(keepReasons),
      avoid_reasons: splitLines(avoidReasons),
    };
    try {
      window.localStorage.setItem("analysis-reviewer", reviewer.trim());
      await api.reviewCase(item.id, payload);
      const label =
        trustStatus === "company_recommended"
          ? "公司推荐"
          : trustStatus === "rejected"
          ? "淘汰"
          : "人工确认";
      setMessage(`案例 #${item.id} 已完成${label}。`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "审核保存失败");
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "w-full rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent";

  return (
    <div className="space-y-6">
      <section className="rounded-[30px] bg-ink px-6 py-8 text-white md:px-9">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-white/45">
              Model analysis verification
            </div>
            <h1 className="mt-3 text-3xl font-semibold">模型拆解连续审核台</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/60">
              对照原图校正拆解，并明确填写希望延续的方法和应避免的问题。只有人工结论会成为公司偏好证据。
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

      <section className="grid gap-3 rounded-2xl border border-line bg-white p-4 md:grid-cols-[1fr_1fr_auto]">
        <select
          value={businessLine}
          onChange={(event) => setBusinessLine(event.target.value)}
          className={inputClass}
        >
          <option value="">全部业务线</option>
          {lines.map((line) => (
            <option key={line} value={line}>
              {line}
            </option>
          ))}
        </select>
        <input
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          placeholder="审核人姓名或岗位 *"
          className={inputClass}
        />
        <div className="rounded-xl bg-canvas px-4 py-2.5 text-sm text-gray-500">
          待审核 {queue.length} 张
        </div>
      </section>

      {loading ? (
        <div className="py-20 text-center text-gray-400">正在加载模型样本…</div>
      ) : !item || !analysis ? (
        <div className="rounded-3xl border border-emerald-200 bg-emerald-50 py-20 text-center">
          <div className="text-xl font-semibold text-emerald-700">
            当前业务线没有待审核模型样本
          </div>
        </div>
      ) : (
        <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(420px,1fr)]">
          <div className="h-fit overflow-hidden rounded-3xl border border-line bg-white xl:sticky xl:top-24">
            {item.image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.image.url}
                alt={item.name}
                className="max-h-[78vh] w-full bg-gray-100 object-contain"
              />
            )}
            <div className="border-t border-line p-4">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>
                  {index + 1}/{queue.length} · {item.business_line}
                </span>
                <span>
                  {categoryLabels[item.asset_category] || item.asset_category}
                </span>
              </div>
              <div className="mt-2 text-sm font-medium">
                #{item.id} · {item.name}
              </div>
            </div>
          </div>

          <div className="space-y-4 rounded-3xl border border-line bg-white p-5 md:p-6">
            <div className="rounded-2xl bg-blue-50 p-4 text-xs leading-6 text-blue-800">
              <div className="font-semibold">
                模型：{analysis.model_name} · 置信度 {analysis.confidence}
              </div>
              <div className="mt-2">
                版式：{analysis.layout.layout_type} /{" "}
                {analysis.layout.alignment}
              </div>
              <div>
                风格：{analysis.style.style_tags.join("、") || "未识别"}
              </div>
              <div>色彩：{analysis.color.description || "未识别"}</div>
              <div>
                可复用方法：
                {analysis.design_rules.reusable_methods.join("；") || "未填写"}
              </div>
            </div>

            <textarea
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="拆解摘要"
              rows={3}
              className={inputClass}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <input
                value={layoutType}
                onChange={(event) => setLayoutType(event.target.value)}
                placeholder="人工校正版式"
                className={inputClass}
              />
              <input
                value={styleTags}
                onChange={(event) => setStyleTags(event.target.value)}
                placeholder="人工校正风格标签，用顿号分隔"
                className={inputClass}
              />
            </div>
            <textarea
              value={colorDescription}
              onChange={(event) => setColorDescription(event.target.value)}
              placeholder="人工校正色彩说明"
              rows={2}
              className={inputClass}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <textarea
                value={keepReasons}
                onChange={(event) => setKeepReasons(event.target.value)}
                placeholder="希望延续的方法，每行一项 *"
                rows={5}
                className={inputClass}
              />
              <textarea
                value={avoidReasons}
                onChange={(event) => setAvoidReasons(event.target.value)}
                placeholder="应避免的问题，每行一项 *"
                rows={5}
                className={inputClass}
              />
            </div>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="审核判断依据"
              rows={3}
              className={inputClass}
            />

            <div className="grid gap-2 sm:grid-cols-3">
              <button
                disabled={saving}
                onClick={() => review("verified", "adopt")}
                className="rounded-xl bg-ink px-4 py-3 text-sm text-white disabled:opacity-50"
              >
                确认可用
              </button>
              <button
                disabled={saving}
                onClick={() => review("company_recommended", "adopt")}
                className="rounded-xl bg-accent px-4 py-3 text-sm text-white disabled:opacity-50"
              >
                公司推荐
              </button>
              <button
                disabled={saving}
                onClick={() => review("rejected", "reject")}
                className="rounded-xl border border-red-200 px-4 py-3 text-sm text-red-500 disabled:opacity-50"
              >
                淘汰样本
              </button>
            </div>
            <div className="flex gap-2">
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
              <div className="rounded-xl bg-canvas p-3 text-xs text-gray-600">
                {message}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
