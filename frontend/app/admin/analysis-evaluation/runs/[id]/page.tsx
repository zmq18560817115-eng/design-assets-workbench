"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AnalysisEvaluationRun, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

const metricLabels: Record<string, string> = {
  pass_rate: "总体通过率", timeout_rate: "超时率", schema_valid_rate: "Schema有效率",
  product_detection_rate: "产品识别率", module_detection_rate: "模块识别率",
  overlap_violation_rate: "重叠违规率",
};

export default function AnalysisRunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<AnalysisEvaluationRun | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => { void analysisEvaluationApi.run(id).then(setRun).catch((e) => setMessage(e.message)); }, [id]);
  if (!run) return <p className="text-sm">{message || "正在读取…"}</p>;
  const sealed = run.dataset_split === "holdout" && !run.unsealed;
  return <div className="space-y-7"><header><h1 className="text-3xl font-semibold">{run.dataset_split === "holdout" ? "Holdout 盲测结果" : "Calibration 回归结果"}</h1>
    <p className="mt-2 text-sm text-gray-500">运行 #{run.id} · {run.run_status} · {run.elapsed_ms}ms</p></header>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(run.aggregate).filter(([key]) => metricLabels[key]).map(([key,value]) =>
      <Card key={key}><div className="text-2xl font-semibold">{Math.round(Number(value) * 100)}%</div><div className="mt-1 text-sm text-gray-500">{metricLabels[key]}</div></Card>)}</div>
    <Card><h2 className="font-semibold">冻结版本快照</h2><p className="mt-3 text-sm">
      {run.version_snapshot.model_name} · {run.version_snapshot.prompt_version} · {run.version_snapshot.validator_version}</p></Card>
    {sealed ? <Card><h2 className="font-semibold">详细结果仍处于密封状态</h2>
      <p className="mt-2 text-sm leading-6 text-gray-500">当前仅显示聚合指标。解封后此 Holdout 将标记为 consumed，不得再次用于盲测。</p>
      <button onClick={async () => {
        if (!window.confirm("解封后当前Holdout将被标记为已消耗，不得再次作为盲测集。")) return;
        try { setRun(await analysisEvaluationApi.unseal(id, "管理员")); } catch (e) { setMessage((e as Error).message); }
      }} className="mt-4 rounded-xl border border-rose-300 px-4 py-2 text-sm text-rose-700">解封详细结果</button></Card>
      : <Card><h2 className="font-semibold">逐案例诊断</h2><div className="mt-4 space-y-2">{run.results?.map((row) =>
        <div key={row.id} className="flex justify-between rounded-xl border border-line p-3 text-sm"><span>条目 #{row.item_id}</span><span>{row.error_code || "通过"}</span></div>)}</div></Card>}
    {message && <p className="text-sm text-rose-600">{message}</p>}
  </div>;
}
