"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AnalysisDataset, analysisEvaluationApi,
} from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

const steps = [
  "创建数据集", "分配 Calibration / Holdout", "建立 Ground Truth",
  "运行 Calibration", "诊断并升级版本", "冻结版本", "独立 Holdout 盲测",
];

export default function AnalysisEvaluationPage() {
  const [datasets, setDatasets] = useState<AnalysisDataset[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    analysisEvaluationApi.datasets().then(setDatasets).catch((e) => setError(e.message));
  }, []);
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[.2em] text-accent">Admin · Visual analysis</div>
          <h1 className="mt-2 text-3xl font-semibold">AI 拆解校准</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-500">
            使用公司素材 Ground Truth 校准多模态拆解。该模块与业务检索验收完全隔离。
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/admin/provider-availability" className="rounded-xl border border-line bg-white px-5 py-3 text-sm">模型服务诊断</Link>
          <Link href="/admin/analysis-evaluation/datasets" className="rounded-xl bg-ink px-5 py-3 text-sm text-white">管理数据集</Link>
        </div>
      </header>
      <div className="grid gap-3 md:grid-cols-7">
        {steps.map((step, index) => (
          <div key={step} className="rounded-2xl border border-line bg-white p-4">
            <div className="text-xs text-accent">0{index + 1}</div>
            <div className="mt-3 text-sm font-medium">{step}</div>
          </div>
        ))}
      </div>
      {error && <p className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
      <section className="grid gap-4 lg:grid-cols-2">
        {datasets.map((dataset) => (
          <Card key={dataset.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">{dataset.name}</h2>
                <p className="mt-1 text-xs text-gray-500">{dataset.dataset_version}</p>
              </div>
              <span className="rounded-full bg-lilac px-3 py-1 text-xs text-accent">{dataset.status}</span>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-2 text-sm">
              <div><b>{dataset.counts.calibration}</b><div className="text-xs text-gray-500">Calibration</div></div>
              <div><b>{dataset.counts.holdout}</b><div className="text-xs text-gray-500">Holdout</div></div>
              <div><b>{dataset.sealed ? "已密封" : "未密封"}</b><div className="text-xs text-gray-500">盲测状态</div></div>
            </div>
            <Link className="mt-5 inline-flex text-sm text-accent" href={`/admin/analysis-evaluation/datasets/${dataset.dataset_version}`}>
              打开数据集 →
            </Link>
          </Card>
        ))}
        {!error && datasets.length === 0 && <Card>尚无拆解校准数据集，请先创建。</Card>}
      </section>
    </div>
  );
}
