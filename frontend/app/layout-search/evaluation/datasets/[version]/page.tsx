"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, Tag } from "@/components/ui";
import { api, BusinessRequirement, CaseOut, LayoutBlueprint, LayoutPattern, LayoutSearchDataset, LayoutSearchEvaluation, LayoutSearchGroundTruth } from "@/lib/api";

type Detail = LayoutSearchDataset & { ground_truth: LayoutSearchGroundTruth[]; evaluation: LayoutSearchEvaluation };

export default function DatasetDetailPage() {
  const { version } = useParams<{version: string}>();
  const decoded = decodeURIComponent(version);
  const [item, setItem] = useState<Detail | null>(null);
  const [requirements, setRequirements] = useState<BusinessRequirement[]>([]);
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [patterns, setPatterns] = useState<LayoutPattern[]>([]);
  const [blueprints, setBlueprints] = useState<LayoutBlueprint[]>([]);
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
  useEffect(() => {
    if (resultType === "case" && resultId) {
      api.layoutBlueprints(resultId).then(setBlueprints).catch(() => setBlueprints([]));
    } else {
      setBlueprints([]);
    }
  }, [resultId, resultType]);
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
  async function editLabel(row: LayoutSearchGroundTruth) {
    const nextReviewer = window.prompt("审核人 reviewer", row.reviewer);
    if (nextReviewer === null) return;
    const nextReason = window.prompt("判断原因 reason", row.reason);
    if (nextReason === null) return;
    const nextRelevance = window.prompt(
      "相关性：relevant / partially_relevant / irrelevant",
      row.expected_relevance
    ) as LayoutSearchGroundTruth["expected_relevance"] | null;
    if (!nextRelevance) return;
    const nextSplit = window.prompt(
      "数据集分组：calibration / holdout", row.dataset_split
    ) as LayoutSearchGroundTruth["dataset_split"] | null;
    if (!nextSplit) return;
    try {
      await api.updateLayoutSearchGroundTruth(row.id, {
        expected_relevance: nextRelevance,
        reviewer: nextReviewer,
        reason: nextReason,
        dataset_split: nextSplit,
      });
      setMessage("标注已更新。"); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "更新失败"); }
  }
  async function deleteLabel(row: LayoutSearchGroundTruth) {
    if (!window.confirm(`删除标注 #${row.id}？`)) return;
    try {
      await api.deleteLayoutSearchGroundTruth(row.id);
      setMessage("标注已删除。"); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "删除失败"); }
  }
  if (!item) return <p>{message || "加载中…"}</p>;
  const frozen = Boolean(item.frozen_at);
  const checks = {
    "真实数据集": item.dataset_kind === "real",
    "公司真实案例至少 50": (item.evaluation.readiness?.company_case_count ?? 0) >= 50,
    "至少 50 个公司案例具有 verified 蓝图": (item.evaluation.readiness?.verified_blueprint_case_count ?? 0) >= 50,
    "verified 模式至少 5": (item.evaluation.readiness?.verified_pattern_count ?? 0) >= 5,
    "confirmed 真实需求至少 10": (item.evaluation.readiness?.confirmed_requirement_count ?? 0) >= 10,
    "总需求至少 10": item.requirement_count >= 10,
    "calibration 至少 7": item.calibration_requirement_count >= 7,
    "holdout 至少 3": item.holdout_requirement_count >= 3,
    "每条需求同时有案例和模式标注": new Set(item.ground_truth.map((r) => r.requirement_id)).size > 0 && [...new Set(item.ground_truth.map((r) => r.requirement_id))].every((id) => new Set(item.ground_truth.filter((r) => r.requirement_id === id).map((r) => r.result_type)).size === 2),
    "reviewer / reason 完整": item.ground_truth.every((r) => r.reviewer.trim() && r.reason.trim()),
  };
  const selectedCase = cases.find((entry) => entry.id === Number(resultId));
  const selectedPattern = patterns.find((entry) => entry.id === Number(resultId));
  const assignedRequirementIds = [...new Set(item.ground_truth.map((row) => row.requirement_id))];
  const splitConflicts = assignedRequirementIds.filter((id) =>
    new Set(item.ground_truth.filter((row) => row.requirement_id === id).map((row) => row.dataset_split)).size > 1
  );
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
    </div>
      {resultType === "case" && selectedCase && <div className="mt-4 grid gap-4 rounded-xl bg-gray-50 p-4 md:grid-cols-[160px_1fr]">
        {selectedCase.image && <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={selectedCase.image.url} alt={selectedCase.name} className="h-40 w-40 rounded-xl object-cover" />
        </>}
        <div className="text-sm"><Link href={`/cases/${selectedCase.id}`} className="font-semibold text-accent">查看案例 #{selectedCase.id}：{selectedCase.name}</Link><p className="mt-2 text-gray-500">{selectedCase.summary}</p><div className="mt-3 flex flex-wrap gap-2">{blueprints.map((blueprint) => <Tag key={blueprint.id}>蓝图 v{blueprint.version} · {blueprint.review_status}</Tag>)}</div></div>
      </div>}
      {resultType === "pattern" && selectedPattern && <div className="mt-4 rounded-xl bg-gray-50 p-4 text-sm"><Link href={`/patterns/${selectedPattern.id}`} className="font-semibold text-accent">查看模式证据 #{selectedPattern.id}：{selectedPattern.name}</Link><p className="mt-2 text-gray-500">{selectedPattern.description}</p><div className="mt-3 flex flex-wrap gap-2"><Tag>证据案例 {selectedPattern.evidence_case_ids_json.length}</Tag><Tag>蓝图 {selectedPattern.evidence_blueprint_ids_json.length}</Tag><Tag>{selectedPattern.review_status}</Tag></div></div>}
    </Card>}
    {splitConflicts.length > 0 && <div className="rounded-xl bg-red-50 p-4 text-sm text-red-700">以下需求同时属于两个 split：{splitConflicts.join("、")}。冻结前必须修正。</div>}
    <Card><h2 className="font-semibold">已分配需求与结构化业务条件</h2><div className="mt-4 grid gap-3">{assignedRequirementIds.map((id) => {
      const requirement = requirements.find((entry) => entry.id === id);
      const rows = item.ground_truth.filter((entry) => entry.requirement_id === id);
      if (!requirement) return null;
      return <div key={id} className="rounded-xl border border-line p-4 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><Link href={`/requirements/${id}`} className="font-semibold text-accent">#{id} {requirement.title}</Link><Tag>{[...new Set(rows.map((row) => row.dataset_split))].join(" / ")}</Tag></div><div className="mt-3 grid gap-2 text-gray-600 md:grid-cols-4"><span>产品：{requirement.product_category || "未填"}</span><span>渠道：{requirement.channel || "未填"}</span><span>目的：{requirement.content_purpose || "未填"}</span><span>阶段：{requirement.campaign_stage || "未填"}</span><span>画布：{requirement.canvas_ratio || "未填"}</span><span>方向：{requirement.orientation || "未填"}</span><span>必需：{requirement.required_modules_json.join("、") || "无"}</span><span>禁止：{requirement.forbidden_modules_json.join("、") || "无"}</span></div></div>;
    })}</div></Card>
    <Card><h2 className="font-semibold">冻结前检查清单</h2><div className="mt-4 grid gap-2 md:grid-cols-2">{Object.entries(checks).map(([label, ok]) => <div key={label} className="flex justify-between rounded-xl bg-gray-50 p-3 text-sm"><span>{label}</span><span className={ok ? "text-green-700" : "text-red-600"}>{ok ? "满足" : "缺失"}</span></div>)}</div></Card>
    <Card><h2 className="font-semibold">准备度与 Task 5</h2><div className="mt-4 grid gap-3 md:grid-cols-4 text-sm"><span>公司案例 {item.evaluation.readiness?.company_case_count ?? 0}</span><span>verified 蓝图案例 {item.evaluation.readiness?.verified_blueprint_case_count ?? 0}</span><span>verified 模式 {item.evaluation.readiness?.verified_pattern_count ?? 0}</span><span>confirmed 需求 {item.evaluation.readiness?.confirmed_requirement_count ?? 0}</span></div><p className="mt-4 text-sm font-medium">{item.evaluation.readiness?.can_enter_task_5 ? "允许进入 Task 5" : "不允许进入 Task 5：真实业务验收尚未通过"}</p><div className="mt-2 flex flex-wrap gap-2">{(item.evaluation.readiness?.blocking_reasons || []).map((r) => <Tag key={r}>{r}</Tag>)}</div></Card>
    <Card><h2 className="font-semibold">Ground Truth（{item.annotation_count}）</h2><div className="mt-4 space-y-2">{item.ground_truth.map((row) => <div key={row.id} className="grid gap-2 rounded-xl border border-line p-3 text-sm md:grid-cols-[1fr_1fr_1fr_1fr_1fr_2fr_auto]"><Link className="text-accent" href={`/requirements/${row.requirement_id}`}>需求 #{row.requirement_id}</Link><span>{row.dataset_split}</span><Link className="text-accent" href={row.result_type === "case" ? `/cases/${row.result_id}` : `/patterns/${row.result_id}`}>{row.result_type} #{row.result_id}</Link><span>{row.expected_relevance}</span><span>{row.reviewer}</span><span>{row.reason}</span>{!frozen && <span className="flex gap-2"><button className="text-accent" onClick={() => editLabel(row)}>编辑</button><button className="text-red-600" onClick={() => deleteLabel(row)}>删除</button></span>}</div>)}</div></Card>
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
