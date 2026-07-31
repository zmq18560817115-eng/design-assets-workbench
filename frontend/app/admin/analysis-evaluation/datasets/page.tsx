"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { AnalysisDataset, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

export default function AnalysisDatasetsPage() {
  const [items, setItems] = useState<AnalysisDataset[]>([]);
  const [message, setMessage] = useState("");
  const load = () => analysisEvaluationApi.datasets().then(setItems).catch((e) => setMessage(e.message));
  useEffect(() => {
    void analysisEvaluationApi.datasets().then(setItems).catch((e) => setMessage(e.message));
  }, []);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await analysisEvaluationApi.createDataset({
        dataset_version: data.get("dataset_version"),
        name: data.get("name"),
        product_category: data.get("product_category"),
        description: data.get("description"),
        created_by: data.get("created_by"),
      });
      event.currentTarget.reset();
      setMessage("数据集已创建");
      load();
    } catch (error) { setMessage((error as Error).message); }
  };
  return (
    <div className="space-y-7">
      <div><Link href="/admin/analysis-evaluation" className="text-sm text-gray-500">← AI 拆解校准</Link>
        <h1 className="mt-3 text-3xl font-semibold">数据集管理</h1></div>
      <Card>
        <form onSubmit={create} className="grid gap-3 md:grid-cols-2">
          {[
            ["dataset_version", "版本，例如 company-layout-v1"],
            ["name", "数据集名称"], ["product_category", "产品分类"],
            ["created_by", "创建人"],
          ].map(([name, placeholder]) => <input key={name} name={name} required={name !== "product_category"}
            placeholder={placeholder} className="rounded-xl border border-line px-3 py-2.5 text-sm" />)}
          <textarea name="description" placeholder="说明" className="rounded-xl border border-line px-3 py-2.5 text-sm md:col-span-2" />
          <button className="rounded-xl bg-ink px-4 py-2.5 text-sm text-white md:col-span-2">创建草稿数据集</button>
        </form>
        {message && <p className="mt-3 text-sm text-gray-600">{message}</p>}
      </Card>
      <div className="grid gap-3">
        {items.map((item) => <Link key={item.id} href={`/admin/analysis-evaluation/datasets/${item.dataset_version}`}
          className="flex items-center justify-between rounded-2xl border border-line bg-white p-5 hover:border-accent">
          <div><b>{item.name}</b><p className="mt-1 text-xs text-gray-500">{item.dataset_version} · {item.product_category || "全部产品"}</p></div>
          <span className="text-sm">{item.counts.calibration} / {item.counts.holdout} · {item.status}</span>
        </Link>)}
      </div>
    </div>
  );
}
