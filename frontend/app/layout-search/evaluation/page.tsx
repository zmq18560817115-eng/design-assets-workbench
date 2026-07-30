"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui";
import { api, LayoutSearchEvaluation } from "@/lib/api";

const labels: Record<string, string> = {
  case_direct_precision_at_5: "案例直接 P@5",
  case_useful_precision_at_10: "案例有用 P@10",
  case_recall_at_10: "案例 R@10",
  pattern_direct_precision_at_3: "模式直接 P@3",
  pattern_useful_precision_at_5: "模式有用 P@5",
  traceability_rate: "可追溯率",
  forbidden_module_violation_count: "禁用模块命中",
  minimum_results_per_requirement: "每需求 ≥10 案例 / ≥3 模式",
};

export default function EvaluationPage() {
  const [report, setReport] = useState<LayoutSearchEvaluation | null>(null);
  const [version, setVersion] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    api.layoutSearchEvaluation().then(setReport).catch((error) => setMessage(error.message));
  }, []);
  async function run() {
    if (!version) return setMessage("请填写已冻结的数据集版本");
    setMessage("正在运行验收检索…");
    try {
      setReport(await api.runLayoutSearchEvaluation(version));
      setMessage("验收检索已完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "运行失败");
    }
  }
  function exportJson() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob(
      [JSON.stringify(report, null, 2)], { type: "application/json" }
    ));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.dataset_version || "not-ready"}-evaluation.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  const metrics = report?.holdout.metrics || {};
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[.2em] text-accent">Acceptance</div>
          <h1 className="mt-2 text-3xl font-bold">真实业务检索验收</h1>
          <p className="mt-2 text-sm text-gray-500">Ground Truth 必须先定义并冻结，之后才能运行验收检索。</p>
        </div>
        <div className="flex gap-2">
          <Link className="rounded-xl border border-line px-4 py-2 text-sm" href="/layout-search/evaluation/datasets">数据集工作台</Link>
          <input className="rounded-xl border border-line px-3 py-2 text-sm" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="数据集版本" />
          <button className="rounded-xl border border-line px-4 py-2 text-sm" onClick={() => api.layoutSearchEvaluation(version).then(setReport)}>查询</button>
          <button className="rounded-xl bg-ink px-4 py-2 text-sm text-white" onClick={run}>重新运行</button>
          <button className="rounded-xl border border-line px-4 py-2 text-sm" onClick={exportJson}>导出 JSON</button>
        </div>
      </div>
      {message && <div className="rounded-xl bg-lilac px-4 py-3 text-sm">{message}</div>}
      <Card>
        <div className="flex items-center justify-between">
          <div><div className="text-sm text-gray-500">当前状态</div><div className="mt-1 text-xl font-semibold">{report?.message || "尚未完成真实业务验收"}</div></div>
          <span className={`rounded-full px-3 py-1 text-xs ${report?.status === "passed" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>{report?.status || "not_ready"}</span>
        </div>
        <div className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
          <div>版本：{report?.dataset_version || "—"}</div><div>标注：{String(report?.dataset.total ?? 0)}</div>
          <div>校准集：{String(report?.dataset.calibration ?? 0)}</div><div>留出集：{String(report?.dataset.holdout ?? 0)}</div>
        </div>
      </Card>
      <Card>
        <h2 className="text-lg font-semibold">真实业务验收准备度</h2>
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          <span>公司真实案例 {report?.readiness?.company_case_count ?? 0}</span>
          <span>verified 蓝图案例 {report?.readiness?.verified_blueprint_case_count ?? 0}</span>
          <span>verified 模式 {report?.readiness?.verified_pattern_count ?? 0}</span>
          <span>confirmed 需求 {report?.readiness?.confirmed_requirement_count ?? 0}</span>
        </div>
        <p className="mt-4 text-sm font-medium">{report?.readiness?.can_enter_task_5 ? "允许进入 Task 5" : "尚不允许进入 Task 5"}</p>
        <p className="mt-2 text-xs text-gray-500">阻塞项：{report?.readiness?.blocking_reasons.join("、") || "等待选择真实数据集"}</p>
      </Card>
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(metrics).filter(([key]) => labels[key]).map(([key, value]) => (
          <Card key={key}><div className="text-sm text-gray-500">{labels[key]}</div><div className="mt-2 text-2xl font-semibold">{value <= 1 ? `${(value * 100).toFixed(1)}%` : value}</div></Card>
        ))}
      </div>
      <Card>
        <h2 className="text-lg font-semibold">留出集门禁</h2>
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          {Object.entries(report?.gates || {}).map(([key, passed]) => (
            <div key={key} className="flex justify-between rounded-xl bg-gray-50 px-4 py-3 text-sm"><span>{labels[key] || key}</span><span className={passed ? "text-green-700" : "text-red-600"}>{passed ? "通过" : "未通过"}</span></div>
          ))}
        </div>
      </Card>
      <Card>
        <h2 className="text-lg font-semibold">逐需求结果</h2>
        <div className="mt-4 space-y-2 text-sm">
          {(report?.overall.requirements || []).map((row) => (
            <div key={String(row.requirement_id)} className="grid gap-2 rounded-xl border border-line px-4 py-3 md:grid-cols-6">
              <span>需求 #{String(row.requirement_id)}</span><span>{String(row.dataset_split)}</span>
              <span>案例 {String(row.returned_case_count)}</span><span>模式 {String(row.returned_pattern_count)}</span>
              <span>P@5 {Number(row.case_direct_precision_at_5 || 0).toFixed(2)}</span><span>{String(row.average_search_elapsed_ms)}ms</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
