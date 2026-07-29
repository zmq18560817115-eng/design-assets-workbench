"use client";

import { useState } from "react";
import { api, CaseOut, CaseReviewInput } from "@/lib/api";
import { Card } from "@/components/ui";

const lines = (items: string[]) => items.join("\n");
const splitLines = (value: string) =>
  value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
const splitTags = (value: string) =>
  value.split(/[，,、]/).map((item) => item.trim()).filter(Boolean);

export function ReviewPanel({
  item,
  onSaved,
}: {
  item: CaseOut;
  onSaved: (value: CaseOut) => void;
}) {
  const a = item.analysis;
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    reviewer: item.reviewer || "",
    trust_status: item.trust_status || "verified",
    review_decision: item.review_decision || "",
    review_notes: item.review_notes || "",
    business_line: item.business_line || "",
    channel: item.channel || "",
    campaign_stage: item.campaign_stage || "",
    business_goal: item.business_goal || "",
    name: item.name,
    summary: item.summary,
    layout_type: a?.layout.layout_type || "",
    alignment: a?.layout.alignment || "",
    hierarchy: lines(a?.layout.hierarchy || []),
    style_tags: (a?.style.style_tags || []).join("、"),
    mood_keywords: (a?.style.mood_keywords || []).join("、"),
    color_description: a?.color.description || "",
    why_good: lines(a?.design_rules.why_good || []),
    reusable_methods: lines(a?.design_rules.reusable_methods || []),
    prompt: a?.prompt || "",
  });

  if (!a) return null;

  const update = (key: string, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const save = async () => {
    if (!form.reviewer.trim()) {
      setMessage("请填写校验人");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const payload: CaseReviewInput = {
        ...form,
        trust_status: form.trust_status as CaseReviewInput["trust_status"],
        review_decision: form.review_decision as CaseReviewInput["review_decision"],
        hierarchy: splitLines(form.hierarchy),
        style_tags: splitTags(form.style_tags),
        mood_keywords: splitTags(form.mood_keywords),
        why_good: splitLines(form.why_good),
        reusable_methods: splitLines(form.reusable_methods),
      };
      const saved = await api.reviewCase(item.id, payload);
      onSaved(saved);
      setMessage(`已保存人工校验版本 v${saved.analysis?.version || ""}`);
    } catch {
      setMessage("保存失败，请检查后端服务");
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "w-full rounded-xl border border-line bg-white px-3 py-2 text-sm text-gray-700 outline-none focus:border-accent";

  return (
    <Card className="border-amber-300 bg-amber-50/50">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between text-left"
      >
        <div>
          <div className="font-semibold text-gray-800">设计师人工校验</div>
          <div className="mt-1 text-xs text-gray-500">
            修正模型结果并沉淀为公司标准答案；每次保存都会生成新版本。
          </div>
        </div>
        <span className="text-sm text-accent">{open ? "收起" : "开始校验"}</span>
      </button>
      {open && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={form.reviewer}
              onChange={(e) => update("reviewer", e.target.value)}
              placeholder="校验人（必填）"
              className={inputClass}
            />
            <select
              value={form.trust_status}
              onChange={(e) => update("trust_status", e.target.value)}
              className={inputClass}
            >
              <option value="verified">已校验</option>
              <option value="company_recommended">公司推荐</option>
              <option value="rejected">不推荐</option>
              <option value="ai_unverified">退回AI未校验</option>
            </select>
            <select
              value={form.review_decision}
              onChange={(e) => update("review_decision", e.target.value)}
              className={inputClass}
            >
              <option value="">采用判断</option>
              <option value="adopt">直接采用</option>
              <option value="adapt">修改后采用</option>
              <option value="reject">不采用</option>
            </select>
            <input
              value={form.business_line}
              onChange={(e) => update("business_line", e.target.value)}
              placeholder="业务线 / 产品线"
              className={inputClass}
            />
            <input
              value={form.channel}
              onChange={(e) => update("channel", e.target.value)}
              placeholder="渠道，如：小红书"
              className={inputClass}
            />
            <input
              value={form.campaign_stage}
              onChange={(e) => update("campaign_stage", e.target.value)}
              placeholder="营销阶段，如：大促预热"
              className={inputClass}
            />
          </div>
          <textarea
            value={form.business_goal}
            onChange={(e) => update("business_goal", e.target.value)}
            placeholder="业务目标与目标用户"
            className={`${inputClass} min-h-20`}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="案例名称"
              className={inputClass}
            />
            <input
              value={form.layout_type}
              onChange={(e) => update("layout_type", e.target.value)}
              placeholder="排版类型"
              className={inputClass}
            />
            <input
              value={form.alignment}
              onChange={(e) => update("alignment", e.target.value)}
              placeholder="对齐方式"
              className={inputClass}
            />
            <input
              value={form.style_tags}
              onChange={(e) => update("style_tags", e.target.value)}
              placeholder="风格标签，用顿号分隔"
              className={inputClass}
            />
            <input
              value={form.mood_keywords}
              onChange={(e) => update("mood_keywords", e.target.value)}
              placeholder="情绪关键词"
              className={inputClass}
            />
            <input
              value={form.color_description}
              onChange={(e) => update("color_description", e.target.value)}
              placeholder="色彩体系说明"
              className={inputClass}
            />
          </div>
          <textarea
            value={form.summary}
            onChange={(e) => update("summary", e.target.value)}
            placeholder="案例总结"
            className={`${inputClass} min-h-20`}
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <textarea
              value={form.hierarchy}
              onChange={(e) => update("hierarchy", e.target.value)}
              placeholder="信息层级，每行一项"
              className={`${inputClass} min-h-32`}
            />
            <textarea
              value={form.why_good}
              onChange={(e) => update("why_good", e.target.value)}
              placeholder="为什么优秀，每行一项"
              className={`${inputClass} min-h-32`}
            />
            <textarea
              value={form.reusable_methods}
              onChange={(e) => update("reusable_methods", e.target.value)}
              placeholder="可复用方法，每行一项"
              className={`${inputClass} min-h-32`}
            />
          </div>
          <textarea
            value={form.prompt}
            onChange={(e) => update("prompt", e.target.value)}
            placeholder="公司校正后的生图提示词"
            className={`${inputClass} min-h-36`}
          />
          <textarea
            value={form.review_notes}
            onChange={(e) => update("review_notes", e.target.value)}
            placeholder="采用/不采用理由，以及需要避免的表达"
            className={`${inputClass} min-h-24`}
          />
          <div className="flex items-center gap-3">
            <button
              onClick={save}
              disabled={saving}
              className="rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存人工校验版本"}
            </button>
            {message && <span className="text-sm text-gray-600">{message}</span>}
          </div>
        </div>
      )}
    </Card>
  );
}
