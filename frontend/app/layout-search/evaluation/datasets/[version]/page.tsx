"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, Tag } from "@/components/ui";
import { api, BusinessRequirement, CaseOut, LayoutPattern, LayoutSearchDataset, LayoutSearchEvaluation, LayoutSearchGroundTruth } from "@/lib/api";

type Detail = LayoutSearchDataset & { ground_truth: LayoutSearchGroundTruth[]; evaluation: LayoutSearchEvaluation };

export default function DatasetDetailPage() {
  const { version } = useParams<{version: string}>();
  const decoded = decodeURIComponent(version);
  const [item, setItem] = useState<Detail | null>(null);
  const [requirements, setRequirements] = useState<BusinessRequirement[]>([]);
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [patterns, setPatterns] = useState<LayoutPattern[]>([]);
  const [requirementId, setRequirementId] = useState("");
  const [resultType, setResultType] = useState<"case" | "pattern">("case");
  const [resultId, setResultId] = useState("");
  const [split, setSplit] = useState<"calibration" | "holdout">("calibration");
  const [relevance, setRelevance] = useState<"relevant" | "partially_relevant" | "irrelevant">("relevant");
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const load = () => api.layoutSearchDataset(decoded).then(setItem).catch((e) => setMessage(e.message));
  useEffect(() => {
    api.layoutSearchDataset(decoded).then(setItem).catch((e) => setMessage(e.message));
    api.businessRequirements().then(setRequirements);
    api.cases().then(setCases);
    api.layoutPatterns({ review_status: "verified" }).then(setPatterns);
  }, [decoded]);
  async function addLabel() {
    try {
      await api.createLayoutSearchGroundTruth({
        requirement_id: Number(requirementId), result_type: resultType,
        result_id: Number(resultId), expected_relevance: relevance,
        reviewer, reason, dataset_version: decoded, dataset_split: split,
      });
      setReason(""); setMessage("标注已添加。"); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "添加失败"); }
  }
  async function freeze() {
    if (!window.confirm("冻结后不可新增、修改或删除标注。确认永久冻结此版本？")) return;
    try { await api.freezeLayoutSearchGroundTruth(decoded); setMessage("数据集已冻结。"); await load(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "冻结失败"); }
  }
  async function run() {
    try { await api.runLayoutSearchEvaluation(decoded); setMessage("验收运行完成。"); await load(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "运行失败"); }
  }
  if (!item) return <p>{message || "加载中…"}</p>;
  const frozen = Boolean(item.frozen_at);
  const checks = {
    "真实数据集": item.dataset_kind === "real",
    "总需求至少 10": item.requirement_count >= 10,
    "calibration 至少 7": item.calibration_requirement_count >= 7,
    "holdout 至少 3": item.holdout_requirement_count >= 3,
    "每条需求同时有案例和模式标注": new Set(item.ground_truth.map((r) => r.requirement_id)).size > 0 && [...new Set(item.ground_truth.map((r) => r.requirement_id))].every((id) => new Set(item.ground_truth.filter((r) => r.requirement_id === id).map((r) => r.result_type)).size === 2),
    "reviewer / reason 完整": item.ground_truth.every((r) => r.reviewer.trim() && r.reason.trim()),
  };
  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><Link href="/layout-search/evaluation/datasets" className="text-xs text-accent">← 数据集列表</Link><h1 className="mt-2 text-3xl font-bold">{item.name}</h1><p className="mt-2 text-sm text-gray-500">{decoded} · 不同需求 {item.requirement_count} · 标注 {item.annotation_count}</p></div><div className="flex gap-2"><button disabled={frozen} className="rounded-xl bg-amber-600 px-4 py-2 text-sm text-white disabled:opacity-40" onClick={freeze}>冻结数据集</button><button disabled={!frozen} className="rounded-xl bg-ink px-4 py-2 text-sm text-white disabled:opacity-40" onClick={run}>运行验收</button><a className="rounded-xl border border-line px-4 py-2 text-sm" href={`/api/layout-search/evaluation/export?dataset_version=${encodeURIComponent(decoded)}`}>完整导出</a></div></div>
    {message && <div className="rounded-xl bg-lilac p-3 text-sm">{message}</div>}
    {!frozen && <Card><h2 className="font-semibold">添加 Ground Truth</h2><div className="mt-4 grid gap-3 md:grid-cols-3">
      <select className="rounded-xl border border-line p-3 text-sm" value={requirementId} onChange={(e) => setRequirementId(e.target.value)}><option value="">选择 confirmed 需求</option>{requirements.filter((r) => r.status === "confirmed").map((r) => <option key={r.id} value={r.id}>#{r.id} {r.title}</option>)}</select>
      <select className="rounded-xl border border-line p-3 text-sm" value={split} onChange={(e) => setSplit(e.target.value as typeof split)}><option value="calibration">calibration</option><option value="holdout">holdout</option></select>
      <select className="rounded-xl border border-line p-3 text-sm" value={resultType} onChange={(e) => { setResultType(e.target.value as typeof resultType); setResultId(""); }}><option value="case">案例</option><option value="pattern">排版模式</option></select>
      <select className="rounded-xl border border-line p-3 text-sm" value={resultId} onChange={(e) => setResultId(e.target.value)}><option value="">选择结果</option>{(resultType === "case" ? cases : patterns).map((r) => <option key={r.id} value={r.id}>#{r.id} {r.name}</option>)}</select>
      <select className="rounded-xl border border-line p-3 text-sm" value={relevance} onChange={(e) => setRelevance(e.target.value as typeof relevance)}><option value="relevant">relevant</option><option value="partially_relevant">partially_relevant</option><option value="irrelevant">irrelevant</option></select>
      <input className="rounded-xl border border-line p-3 text-sm" placeholder="reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
      <input className="rounded-xl border border-line p-3 text-sm md:col-span-2" placeholder="判断理由（必填）" value={reason} onChange={(e) => setReason(e.target.value)} />
      <button className="rounded-xl bg-ink px-4 py-3 text-sm text-white" onClick={addLabel}>添加标注</button>
    </div></Card>}
    <Card><h2 className="font-semibold">冻结前检查清单</h2><div className="mt-4 grid gap-2 md:grid-cols-2">{Object.entries(checks).map(([label, ok]) => <div key={label} className="flex justify-between rounded-xl bg-gray-50 p-3 text-sm"><span>{label}</span><span className={ok ? "text-green-700" : "text-red-600"}>{ok ? "满足" : "缺失"}</span></div>)}</div></Card>
    <Card><h2 className="font-semibold">准备度与 Task 5</h2><div className="mt-4 grid gap-3 md:grid-cols-4 text-sm"><span>公司案例 {item.evaluation.readiness?.company_case_count ?? 0}</span><span>verified 蓝图案例 {item.evaluation.readiness?.verified_blueprint_case_count ?? 0}</span><span>verified 模式 {item.evaluation.readiness?.verified_pattern_count ?? 0}</span><span>confirmed 需求 {item.evaluation.readiness?.confirmed_requirement_count ?? 0}</span></div><p className="mt-4 text-sm font-medium">{item.evaluation.readiness?.can_enter_task_5 ? "允许进入 Task 5" : "不允许进入 Task 5：真实业务验收尚未通过"}</p><div className="mt-2 flex flex-wrap gap-2">{(item.evaluation.readiness?.blocking_reasons || []).map((r) => <Tag key={r}>{r}</Tag>)}</div></Card>
    <Card><h2 className="font-semibold">Ground Truth（{item.annotation_count}）</h2><div className="mt-4 space-y-2">{item.ground_truth.map((row) => <div key={row.id} className="grid gap-2 rounded-xl border border-line p-3 text-sm md:grid-cols-6"><Link className="text-accent" href={`/requirements/${row.requirement_id}`}>需求 #{row.requirement_id}</Link><span>{row.dataset_split}</span><Link className="text-accent" href={row.result_type === "case" ? `/cases/${row.result_id}` : `/patterns/${row.result_id}`}>{row.result_type} #{row.result_id}</Link><span>{row.expected_relevance}</span><span>{row.reviewer}</span><span>{row.reason}</span></div>)}</div></Card>
    <Card><h2 className="font-semibold">误报与漏报</h2><div className="mt-4 space-y-3">{item.evaluation.overall.requirements.map((row) => {
      const falsePositives = row.false_positives as { case?: number[]; pattern?: number[] } | undefined;
      const falseNegatives = row.false_negatives as { case?: number[]; pattern?: number[] } | undefined;
      return <div key={String(row.requirement_id)} className="rounded-xl border border-line p-3 text-sm">
        <div className="font-medium">需求 #{String(row.requirement_id)} · {String(row.dataset_split)}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(falsePositives?.case || []).map((id) => <Link key={`fpc-${id}`} href={`/cases/${id}`} className="text-red-600">误报案例 #{id}</Link>)}
          {(falsePositives?.pattern || []).map((id) => <Link key={`fpp-${id}`} href={`/patterns/${id}`} className="text-red-600">误报模式 #{id}</Link>)}
          {(falseNegatives?.case || []).map((id) => <Link key={`fnc-${id}`} href={`/cases/${id}`} className="text-amber-700">漏报案例 #{id}</Link>)}
          {(falseNegatives?.pattern || []).map((id) => <Link key={`fnp-${id}`} href={`/patterns/${id}`} className="text-amber-700">漏报模式 #{id}</Link>)}
        </div>
      </div>;
    })}</div></Card>
  </div>;
}
