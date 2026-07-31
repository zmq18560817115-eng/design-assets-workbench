"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AnalysisDataset, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

export default function AnalysisDatasetDetailPage() {
  const { version } = useParams<{ version: string }>();
  const [dataset, setDataset] = useState<AnalysisDataset | null>(null);
  const [message, setMessage] = useState("");
  const load = () => analysisEvaluationApi.dataset(version).then(setDataset).catch((e) => setMessage(e.message));
  useEffect(load, [version]);
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
              <Link key={item.id} href={`/cases/${item.case_id}`} className="flex justify-between rounded-xl border border-line p-3 text-sm">
                <span>案例 #{item.case_id}</span><span>{item.gt_status}</span>
              </Link>)}
            {!dataset.items.some((item) => item.dataset_split === split) && <p className="text-sm text-gray-400">暂无案例</p>}
          </div>
        </Card>)}
      </div>
    </div>
  );
}
