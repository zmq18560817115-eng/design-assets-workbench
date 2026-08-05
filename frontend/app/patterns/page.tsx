"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Tag } from "@/components/ui";

type History = { id: number; action: string; reviewer: string; reviewer_role: string; notes: string; created_at: string };
type Candidate = {
  candidate_id: string; pattern_name_suggestion: string; category: string; case_count: number;
  representative_ids: number[]; product_position: string; title_position: string; reading_order: string;
  suitable_pages: string[]; unsuitable_pages: string[]; required_modules: string[]; optional_modules: string[];
  evidence_annotation_ids: number[]; average_information_density: string; average_whitespace_ratio: number;
  decision: "pending" | "keep" | "merge" | "reject"; owner_confirmed: boolean; owner_reviewer: string;
  merge_target_id: string; formal_pattern_id?: number; formal_status: "not_created" | "draft" | "verified";
  missing_requirements: string[]; current_step: number; is_core_pending: boolean; history: History[];
};
type Counts = { total: number; decision_completed: number; pending: number; owner_confirmed: number; formal_patterns: number };

const decisionLabel = { pending: "未处理", keep: "保留", merge: "合并", reject: "拒绝" };
const actionLabel: Record<string, string> = {
  legacy_snapshot: "旧状态快照", keep: "保留为独立模式", merge: "合并到同品类模式", reject: "拒绝该模式",
  rename: "修改名称", owner_confirm: "设计负责人确认", owner_unconfirm: "取消负责人确认",
  formal_pattern_created: "创建正式模式", formal_verified: "正式验证",
};

export default function LayoutPatternsPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [counts, setCounts] = useState<Counts>({ total: 0, decision_completed: 0, pending: 0, owner_confirmed: 0, formal_patterns: 0 });
  const [showAll, setShowAll] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [reviewer, setReviewer] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/ai-layout-candidates", { cache: "no-store" });
    const data = response.ok ? await response.json() : { candidates: [], counts: { total: 0, decision_completed: 0, pending: 0, owner_confirmed: 0, formal_patterns: 0 } };
    setCandidates(data.candidates ?? []); setCounts(data.counts);
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function act(candidate: Candidate, action: string) {
    setBusy(candidate.candidate_id); setMessage("");
    const ownerAction = ["owner_confirm", "owner_unconfirm", "publish"].includes(action);
    const response = await fetch("/api/ai-layout-candidates", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: candidate.candidate_id, action, reviewer, reviewer_role: ownerAction ? "design_owner" : "reviewer", name: names[candidate.candidate_id], merge_target_id: targets[candidate.candidate_id] }),
    });
    const data = await response.json().catch(() => ({}));
    setMessage(response.ok ? "操作已追加到审核历史。" : String(data.detail ?? "操作失败"));
    if (response.ok) await load(); setBusy("");
  }

  const visible = useMemo(() => showAll ? candidates : candidates.filter(item => item.is_core_pending), [candidates, showAll]);
  return <div>
    <header className="rounded-3xl bg-ink p-6 text-white">
      <div className="text-xs uppercase tracking-[.2em] text-indigo-200">P3.2-D2 · Formal publication</div>
      <h1 className="mt-2 text-3xl font-bold">公司排版模式人工发布</h1>
      <p className="mt-3 text-sm text-slate-200">1. 选择保留、合并或拒绝　→　2. 设计负责人确认　→　3. 创建并确认正式模式</p>
      <p className="mt-2 text-xs text-slate-300">合并仅允许同品类。所有操作追加留痕；系统不会自动处理或自动发布。</p>
    </header>

    <section className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
      {[["候选总数", counts.total], ["已完成决定", counts.decision_completed], ["待处理", counts.pending], ["负责人已确认", counts.owner_confirmed], ["正式模式数量", counts.formal_patterns]].map(([label, value]) => <Card key={String(label)}><p className="text-xs text-gray-500">{label}</p><strong className="mt-1 block text-2xl">{value}</strong></Card>)}
    </section>

    <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
      <div><strong>{showAll ? "全部候选与归档" : "需要人工处理"}</strong><p className="text-xs text-gray-500">当前显示 {visible.length} 项</p></div>
      <div className="flex gap-2"><input value={reviewer} onChange={event => setReviewer(event.target.value)} placeholder="操作人／设计负责人姓名" className="rounded-xl border border-line px-3 py-2 text-sm" /><button onClick={() => setShowAll(value => !value)} className="rounded-xl border border-line bg-white px-4 py-2 text-sm">{showAll ? "只看待处理" : "查看全部候选及归档"}</button></div>
    </div>
    {message && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}

    <div className="mt-5 grid gap-5 lg:grid-cols-2">
      {visible.map(candidate => {
        const sameCategory = candidates.filter(item => item.category === candidate.category && item.candidate_id !== candidate.candidate_id);
        const canOwnerConfirm = candidate.decision === "keep" && !candidate.owner_confirmed && Boolean(reviewer.trim());
        const canPublish = candidate.missing_requirements.length === 0 && Boolean(reviewer.trim()) && candidate.formal_status !== "verified";
        return <Card key={candidate.candidate_id} className="h-full">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><Tag>{candidate.category}</Tag><h2 className="mt-2 text-lg font-semibold">{candidate.pattern_name_suggestion}</h2><p className="mt-1 text-xs text-gray-500">{candidate.candidate_id}</p></div><Tag>当前步骤 {candidate.current_step}/3</Tag></div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-xs"><div className="rounded-lg bg-gray-50 p-2"><span className="text-gray-500">人工决定</span><strong className="mt-1 block">{decisionLabel[candidate.decision]}</strong></div><div className="rounded-lg bg-gray-50 p-2"><span className="text-gray-500">负责人确认</span><strong className="mt-1 block">{candidate.owner_confirmed ? `已确认 · ${candidate.owner_reviewer}` : "未确认"}</strong></div><div className="rounded-lg bg-gray-50 p-2"><span className="text-gray-500">正式模式</span><strong className="mt-1 block">{candidate.formal_status === "not_created" ? "未创建" : candidate.formal_status}</strong></div></div>
          <p className="mt-3 text-sm text-gray-600">产品常见于{candidate.product_position}，文字常见于{candidate.title_position}；{candidate.reading_order}。</p>
          <div className="mt-3 flex flex-wrap gap-2"><Tag>案例 {candidate.case_count}</Tag><Tag>代表案例 {candidate.representative_ids.join("、")}</Tag><Tag>{candidate.average_information_density}</Tag></div>
          <details className="mt-3 rounded-xl border border-line p-3 text-xs"><summary className="cursor-pointer font-medium">查看代表案例</summary><div className="mt-3 grid grid-cols-2 gap-2">{candidate.representative_ids.map(id => <div key={id} className="relative aspect-square overflow-hidden rounded-lg bg-gray-50"><Image src={`/api/layout-annotations/${id}/original-image`} alt={`代表案例 ${id}`} fill unoptimized className="object-contain" /></div>)}</div></details>
          <details className="mt-2 rounded-xl border border-line p-3 text-xs" data-testid="technical-details"><summary className="cursor-pointer font-medium">查看技术详情</summary><div className="mt-2 space-y-1 text-gray-500"><p>适用：{candidate.suitable_pages.join("、")}</p><p>不适用：{candidate.unsuitable_pages.join("、")}</p><p>必需模块：{candidate.required_modules.join("、")}</p><p>可选模块：{candidate.optional_modules.join("、") || "无"}</p><p>证据：{candidate.evidence_annotation_ids.join("、")}</p><p>留白：{Math.round(candidate.average_whitespace_ratio * 100)}%</p></div></details>

          {candidate.missing_requirements.length > 0 && <div className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-800"><strong>还缺：</strong>{candidate.missing_requirements.join("；")}</div>}
          {candidate.formal_pattern_id && <Link href={`/patterns/${candidate.formal_pattern_id}`} className="mt-3 inline-block text-sm font-semibold text-accent">查看正式模式 #{candidate.formal_pattern_id}</Link>}

          <div className="mt-4 space-y-2">
            <div className="flex gap-2"><input value={names[candidate.candidate_id] ?? candidate.pattern_name_suggestion} onChange={event => setNames(current => ({ ...current, [candidate.candidate_id]: event.target.value }))} className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm" /><button disabled={busy === candidate.candidate_id} onClick={() => act(candidate, "rename")} className="rounded-lg border px-3 py-2 text-xs disabled:opacity-40">修改名称</button></div>
            <div className="flex flex-wrap gap-2"><button disabled={busy === candidate.candidate_id || candidate.formal_status === "verified"} onClick={() => act(candidate, "keep")} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs text-white disabled:opacity-40">保留为独立模式</button><button disabled={busy === candidate.candidate_id || candidate.formal_status === "verified"} onClick={() => act(candidate, "reject")} className="rounded-lg bg-rose-600 px-3 py-2 text-xs text-white disabled:opacity-40">拒绝该模式</button></div>
            <div className="flex gap-2"><select value={targets[candidate.candidate_id] ?? ""} onChange={event => setTargets(current => ({ ...current, [candidate.candidate_id]: event.target.value }))} className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">选择同品类合并目标</option>{sameCategory.map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.pattern_name_suggestion}</option>)}</select><button disabled={!targets[candidate.candidate_id] || busy === candidate.candidate_id || candidate.formal_status === "verified"} onClick={() => act(candidate, "merge")} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white disabled:opacity-40">合并到同品类模式</button></div>
            <div className="flex flex-wrap gap-2"><button disabled={!canOwnerConfirm || busy === candidate.candidate_id} title={!canOwnerConfirm ? "先保留模式并填写负责人姓名" : ""} onClick={() => act(candidate, "owner_confirm")} className="rounded-lg bg-ink px-3 py-2 text-xs text-white disabled:opacity-40">设计负责人确认</button>{candidate.owner_confirmed && <button disabled={!reviewer.trim() || busy === candidate.candidate_id} onClick={() => act(candidate, "owner_unconfirm")} className="rounded-lg border px-3 py-2 text-xs disabled:opacity-40">取消确认</button>}<button disabled={!canPublish || busy === candidate.candidate_id} title={!canPublish ? candidate.missing_requirements.join("；") : ""} onClick={() => act(candidate, "publish")} className="rounded-lg bg-accent px-3 py-2 text-xs text-white disabled:opacity-40">创建并发布正式模式</button></div>
          </div>

          <details className="mt-4 rounded-xl border border-line p-3 text-xs" open={candidate.history.length > 0}><summary className="cursor-pointer font-medium">操作历史（{candidate.history.length}）</summary><ol className="mt-2 space-y-2">{candidate.history.map(event => <li key={event.id} className="border-l-2 border-gray-200 pl-3"><strong>{actionLabel[event.action] ?? event.action}</strong><span className="ml-2 text-gray-500">{event.reviewer || "系统迁移"} · {event.reviewer_role}</span><p className="text-gray-400">{new Date(event.created_at).toLocaleString("zh-CN")}{event.notes ? ` · ${event.notes}` : ""}</p></li>)}</ol></details>
        </Card>;
      })}
    </div>
  </div>;
}
