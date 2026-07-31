"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AnalysisDataset, AnalysisRuntimeVersion, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

export default function AnalysisDatasetDetailPage() {
  const { version } = useParams<{ version: string }>();
  const [dataset, setDataset] = useState<AnalysisDataset | null>(null);
  const [message, setMessage] = useState("");
  const [versions, setVersions] = useState<AnalysisRuntimeVersion[]>([]);
  const [runtimeId, setRuntimeId] = useState("");
  const load = () => analysisEvaluationApi.dataset(version).then(setDataset).catch((e) => setMessage(e.message));
  useEffect(() => {
    void analysisEvaluationApi.dataset(version).then(setDataset).catch((e) => setMessage(e.message));
    void analysisEvaluationApi.versions().then((rows) => {
      setVersions(rows);
      if (rows[0]) setRuntimeId(String(rows[0].id));
    }).catch(() => undefined);
  }, [version]);
  const execute = async (split: "calibration" | "holdout") => {
    if (!runtimeId) return setMessage("请先创建 Prompt / Validator 版本");
    if (split === "holdout" && !window.confirm("本次运行会消耗当前Holdout。运行结果不能用于直接修改当前版本。")) return;
    try {
      const run = await analysisEvaluationApi.execute({
        dataset_version: version, dataset_split: split,
        runtime_version_id: Number(runtimeId), created_by: "管理员",
        confirm_consume_holdout: split === "holdout",
      });
      window.location.href = `/admin/analysis-evaluation/runs/${run.id}`;
    } catch (error) { setMessage((error as Error).message); }
  };
  const assign = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await analysisEvaluationApi.assignItem(version, {
        case_id: Number(data.get("case_id")),
        dataset_split: data.get("dataset_split"),
        reviewer: data.get("reviewer"),
        reason: data.get("reason"),
      });
      event.currentTarget.reset(); setMessage("案例已分配"); load();
    } catch (error) { setMessage((error as Error).message); }
  };
  if (!dataset) return <p className="text-sm text-gray-500">{message || "正在读取…"}</p>;
  return (
    <div className="space-y-7">
      <header><Link href="/admin/analysis-evaluation/datasets" className="text-sm text-gray-500">← 数据集管理</Link>
        <div className="mt-3 flex flex-wrap items-center gap-3"><h1 className="text-3xl font-semibold">{dataset.name}</h1>
          <span className="rounded-full bg-lilac px-3 py-1 text-xs text-accent">{dataset.status}</span></div>
        <p className="mt-2 text-sm text-gray-500">{dataset.dataset_version} · Calibration {dataset.counts.calibration} · Holdout {dataset.counts.holdout}</p>
      </header>
      <Card>
        <h2 className="font-semibold">分配案例</h2>
        <p className="mt-1 text-xs text-gray-500">同一案例不能同时进入两个 split；开始校准后分配将锁定。</p>
        <form onSubmit={assign} className="mt-4 grid gap-3 md:grid-cols-4">
          <input name="case_id" required type="number" min="1" placeholder="案例 ID" className="rounded-xl border border-line px-3 py-2 text-sm" />
          <select name="dataset_split" className="rounded-xl border border-line px-3 py-2 text-sm"><option value="calibration">Calibration</option><option value="holdout">Holdout（密封）</option></select>
          <input name="reviewer" placeholder="审核人" className="rounded-xl border border-line px-3 py-2 text-sm" />
          <input name="reason" placeholder="分配说明" className="rounded-xl border border-line px-3 py-2 text-sm" />
          <button className="rounded-xl bg-ink px-4 py-2 text-sm text-white md:col-span-4">分配案例</button>
        </form>
        {message && <p className="mt-3 text-sm text-gray-600">{message}</p>}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {(["calibration", "holdout"] as const).map((split) => <Card key={split}>
          <h2 className="font-semibold">{split === "calibration" ? "Calibration 可诊断集" : "Holdout 密封集"}</h2>
          <div className="mt-4 space-y-2">
            {dataset.items.filter((item) => item.dataset_split === split).map((item) =>
              <Link key={item.id} href={`/admin/analysis-evaluation/datasets/${version}/items/${item.id}`} className="flex justify-between rounded-xl border border-line p-3 text-sm">
                <span>案例 #{item.case_id}</span><span>{item.gt_status}</span>
              </Link>)}
            {!dataset.items.some((item) => item.dataset_split === split) && <p className="text-sm text-gray-400">暂无案例</p>}
          </div>
        </Card>)}
      </div>
      <Card>
        <h2 className="font-semibold">运行与冻结</h2>
        <select value={runtimeId} onChange={(event) => setRuntimeId(event.target.value)}
          className="mt-4 w-full rounded-xl border border-line px-3 py-2 text-sm">
          <option value="">选择模型 / Prompt / Validator 版本</option>
          {versions.map((item) => <option key={item.id} value={item.id}>{item.model_name} · {item.prompt_version} · {item.validator_version} · {item.status}</option>)}
        </select>
        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={() => execute("calibration")} className="rounded-xl bg-ink px-4 py-2 text-sm text-white">运行 Calibration</button>
          <button onClick={async () => {
            try { await analysisEvaluationApi.freezeVersion({ dataset_version: version, runtime_version_id: Number(runtimeId), actor: "管理员" }); setMessage("版本已冻结，Holdout 已密封"); load(); }
            catch (error) { setMessage((error as Error).message); }
          }} className="rounded-xl border border-line px-4 py-2 text-sm">冻结版本</button>
          <button onClick={() => execute("holdout")} className="rounded-xl bg-accent px-4 py-2 text-sm text-white">执行独立 Holdout</button>
        </div>
      </Card>
    </div>
  );
}
