"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { Card, Tag } from "@/components/ui";

type Decision = "keep" | "merge" | "reject" | "human";
type Candidate = {
  candidate_id: string; pattern_name_suggestion: string; category: string; case_count: number;
  representative_ids: number[]; evidence_annotation_ids: number[]; product_position: string;
  title_position: string; reading_order: string; average_information_density: string;
  average_whitespace_ratio: number; average_product_area: number; layout_region_range: number[];
  product_region_range: number[]; text_region_range: number[]; required_modules: string[];
  optional_modules: string[]; suitable_pages: string[]; unsuitable_pages: string[];
  system_recommendation: Decision; recommendation_reason: string; merge_target_id?: string;
  overlap_with_merge_target: number; is_core_pending: boolean; human_review_status?: string;
};

const decisionLabel: Record<Decision, string> = { keep: "保留", merge: "合并", reject: "拒绝", human: "需要人工判断" };

export default function LayoutPatternsPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({});
  const [reviewer, setReviewer] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const response = await fetch("/api/ai-layout-candidates", { cache: "no-store" });
    const data = response.ok ? await response.json() : { candidates: [] };
    setCandidates(data.candidates ?? []);
  }
  useEffect(() => { void load(); }, []);

  async function update(candidate: Candidate, action: "rename" | "keep" | "merge" | "reject" | "owner_confirm") {
    const response = await fetch("/api/ai-layout-candidates", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: candidate.candidate_id, action, name: names[candidate.candidate_id], merge_target_id: mergeTargets[candidate.candidate_id] ?? candidate.merge_target_id, reviewer }),
    });
    setMessage(response.ok ? "审核决定已归档；正式 verified 写入为 0。" : await response.text());
    if (response.ok) await load();
  }

  const visible = useMemo(() => showAll ? candidates : candidates.filter(item => item.is_core_pending), [candidates, showAll]);

  return <div>
    <header className="rounded-3xl bg-ink p-6 text-white">
      <div className="text-xs uppercase tracking-[.2em] text-indigo-200">P3.2-D · Pattern review</div>
      <h1 className="mt-2 text-3xl font-bold">公司核心排版模式审核</h1>
      <p className="mt-3 text-sm leading-6 text-slate-200">当前任务：确认公司核心排版模式。完成后进入真实业务检索验收。</p>
      <p className="mt-1 text-xs text-slate-300">候选审核只归档人工决定，不会自动删除记录，也不会自动写入 verified。</p>
    </header>

    <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
      <div><strong>{showAll ? "全部16个候选" : "待人工确认的核心候选"}</strong><p className="mt-1 text-xs text-gray-500">当前显示 {visible.length} 项 · 建议核心模式 6 项</p></div>
      <button onClick={() => setShowAll(value => !value)} className="rounded-xl border border-line bg-white px-4 py-2 text-sm">{showAll ? "只看核心待审核" : "查看全部候选及归档"}</button>
    </div>
    {message && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}

    <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
      {visible.map(candidate => <Card key={candidate.candidate_id} className="h-full">
        <div className="flex items-start justify-between gap-3"><div><Tag>{candidate.category}</Tag><h2 className="mt-2 font-semibold">{names[candidate.candidate_id] ?? candidate.pattern_name_suggestion}</h2></div><Tag>{decisionLabel[candidate.system_recommendation]}</Tag></div>
        <p className="mt-3 text-sm leading-6 text-gray-600">产品常见于{candidate.product_position}，文字常见于{candidate.title_position}；{candidate.reading_order}。</p>
        <div className="mt-3 flex flex-wrap gap-2"><Tag>案例 {candidate.case_count}</Tag><Tag>产品：{candidate.product_position}</Tag><Tag>文字：{candidate.title_position}</Tag></div>
        <dl className="mt-4 grid gap-2 text-xs leading-5"><div><dt className="font-semibold">代表案例</dt><dd>{candidate.representative_ids.join("、")}</dd></div><div><dt className="font-semibold">阅读顺序</dt><dd>{candidate.reading_order}</dd></div><div><dt className="font-semibold">适用页面</dt><dd>{candidate.suitable_pages.join("、")}</dd></div><div><dt className="font-semibold">不适用页面</dt><dd>{candidate.unsuitable_pages.join("、")}</dd></div><div><dt className="font-semibold">系统建议</dt><dd>{decisionLabel[candidate.system_recommendation]}：{candidate.recommendation_reason}</dd></div></dl>
        <details className="mt-4 rounded-xl border border-line p-3 text-xs">
          <summary className="cursor-pointer font-medium">查看代表案例</summary>
          <div className="mt-3 grid grid-cols-2 gap-2">{candidate.representative_ids.map(id => <div key={id} className="relative aspect-square overflow-hidden rounded-lg bg-gray-50"><Image src={`/api/layout-annotations/${id}/original-image`} alt={`代表案例 ${id}`} fill unoptimized className="object-contain" /></div>)}</div>
        </details>
        <details className="mt-2 rounded-xl border border-line p-3 text-xs" data-testid="technical-details">
          <summary className="cursor-pointer font-medium">查看技术详情</summary>
          <div className="mt-3 space-y-1 text-gray-500"><p>产品面积：{Math.round(candidate.average_product_area * 100)}%</p><p>留白比例：{Math.round(candidate.average_whitespace_ratio * 100)}%</p><p>信息密度：{candidate.average_information_density}</p><p>排版模块范围：{candidate.layout_region_range.join("–")}</p><p>产品模块范围：{candidate.product_region_range.join("–")}</p><p>文字模块范围：{candidate.text_region_range.join("–")}</p><p>必需模块：{candidate.required_modules.join("、")}</p><p>可选模块：{candidate.optional_modules.join("、")}</p><p>合并目标重合案例：{candidate.overlap_with_merge_target}</p><p>来源：{candidate.evidence_annotation_ids.join("、")}</p></div>
        </details>
        <div className="mt-4 grid gap-2">
          <input value={names[candidate.candidate_id] ?? candidate.pattern_name_suggestion} onChange={event => setNames(current => ({ ...current, [candidate.candidate_id]: event.target.value }))} className="rounded-lg border border-line px-3 py-2 text-sm" aria-label="模式名称" />
          <select value={mergeTargets[candidate.candidate_id] ?? candidate.merge_target_id ?? ""} onChange={event => setMergeTargets(current => ({ ...current, [candidate.candidate_id]: event.target.value }))} className="rounded-lg border border-line bg-white px-3 py-2 text-sm" aria-label="合并目标"><option value="">选择合并目标</option>{candidates.filter(item => item.candidate_id !== candidate.candidate_id).map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.pattern_name_suggestion}</option>)}</select>
          <div className="flex flex-wrap gap-2"><button onClick={() => update(candidate, "rename")} className="rounded-lg border px-3 py-2 text-xs">修改名称</button><button onClick={() => update(candidate, "keep")} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs text-white">保留模式</button><button onClick={() => update(candidate, "merge")} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white">合并模式</button><button onClick={() => update(candidate, "reject")} className="rounded-lg bg-rose-600 px-3 py-2 text-xs text-white">拒绝模式</button></div>
          <div className="flex gap-2"><input value={reviewer} onChange={event => setReviewer(event.target.value)} placeholder="设计负责人姓名" className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm" /><button onClick={() => update(candidate, "owner_confirm")} className="rounded-lg bg-ink px-3 py-2 text-xs text-white">负责人确认</button></div>
        </div>
      </Card>)}
    </div>
  </div>;
}
