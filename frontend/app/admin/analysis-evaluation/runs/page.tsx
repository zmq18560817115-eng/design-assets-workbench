"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AnalysisEvaluationRun, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

export default function AnalysisRunsPage() {
  const [runs, setRuns] = useState<AnalysisEvaluationRun[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    void analysisEvaluationApi.runs().then(setRuns).catch((e) => setError(e.message));
  }, []);
  return <div className="space-y-7"><header><h1 className="text-3xl font-semibold">运行历史</h1>
    <p className="mt-2 text-sm text-gray-500">每次运行保留数据集、模型、Prompt 和 Validator 的不可变快照。</p></header>
    {error && <p className="text-sm text-rose-600">{error}</p>}
    <div className="grid gap-4">{runs.map((run) => <Link href={`/admin/analysis-evaluation/runs/${run.id}`} key={run.id}>
      <Card className="transition hover:border-accent"><div className="flex flex-wrap justify-between gap-3">
        <div><b>#{run.id} · {run.dataset_split}</b><p className="mt-1 text-xs text-gray-500">
          {run.version_snapshot.model_name} · {run.version_snapshot.prompt_version} · {run.version_snapshot.validator_version}</p></div>
        <span className="rounded-full bg-lilac px-3 py-1 text-xs text-accent">{run.run_status}</span>
      </div></Card></Link>)}</div></div>;
}
