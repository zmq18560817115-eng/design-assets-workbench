"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, CaseOut } from "@/lib/api";
import { AnalysisDataset, AnalysisDatasetItem, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

const initialModules = JSON.stringify([
  { id: "product-1", type: "product_image", label: "产品主体", x: 0.2, y: 0.25, width: 0.6, height: 0.5, importance: 1, priority: 1, confidence: 1 },
  { id: "title-1", type: "main_title", label: "主要文字", x: 0.1, y: 0.08, width: 0.8, height: 0.12, importance: 1, priority: 1, confidence: 1 },
], null, 2);

export default function GroundTruthEditorPage() {
  const { version, itemId } = useParams<{ version: string; itemId: string }>();
  const [dataset, setDataset] = useState<AnalysisDataset | null>(null);
  const [item, setItem] = useState<AnalysisDatasetItem | null>(null);
  const [caseItem, setCaseItem] = useState<CaseOut | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void analysisEvaluationApi.dataset(version).then((data) => {
      setDataset(data);
      const found = data.items.find((row) => row.id === Number(itemId));
      setItem(found || null);
      if (found) void api.case(found.case_id).then(setCaseItem);
    }).catch((error) => setMessage(error.message));
  }, [itemId, version]);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      const modules = JSON.parse(String(data.get("modules") || "[]"));
      const productRegions = modules.filter((row: { type?: string }) => row.type === "product_image")
        .map(({ x, y, width, height }: { x: number; y: number; width: number; height: number }) => ({ x, y, width, height }));
      const textRegions = modules.filter((row: { type?: string }) => ["main_title","subtitle","body_text","selling_point"].includes(row.type || ""))
        .map(({ x, y, width, height }: { x: number; y: number; width: number; height: number }) => ({ x, y, width, height }));
      const saved = await analysisEvaluationApi.saveGroundTruth(version, itemId, {
        has_product: data.get("has_product") === "on",
        product_regions: productRegions, primary_text_regions: textRegions,
        modules, containment: JSON.parse(String(data.get("containment") || "[]")),
        allowed_overlaps: JSON.parse(String(data.get("allowed_overlaps") || "[]")),
        reviewer: data.get("reviewer"), reason: data.get("reason"),
      });
      setItem(saved); setMessage("Ground Truth 已保存");
    } catch (error) { setMessage(`保存失败：${(error as Error).message}`); }
  };
  if (!dataset || !item) return <p className="text-sm">{message || "正在读取…"}</p>;
  return <div className="space-y-7">
    <header><Link href={`/admin/analysis-evaluation/datasets/${version}`} className="text-sm text-gray-500">← 返回数据集</Link>
      <h1 className="mt-3 text-3xl font-semibold">建立 Ground Truth</h1>
      <p className="mt-2 text-sm text-gray-500">{dataset.name} · {item.dataset_split} · 案例 #{item.case_id}</p></header>
    <div className="grid gap-6 lg:grid-cols-[minmax(320px,.8fr)_1.2fr]">
      <Card>{caseItem?.image && <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={caseItem.image.url} alt={caseItem.name} className="mx-auto max-h-[700px] w-auto object-contain" />
      </>}
        <p className="mt-3 text-sm font-medium">{caseItem?.name}</p></Card>
      <Card><form onSubmit={save} className="space-y-4">
        <label className="flex items-center gap-2 text-sm"><input name="has_product" type="checkbox" defaultChecked />存在明确产品主体</label>
        <label className="block text-xs text-gray-500">排版模块与坐标 JSON
          <textarea name="modules" defaultValue={item.ground_truth?.modules ? JSON.stringify(item.ground_truth.modules, null, 2) : initialModules}
            className="mt-1 min-h-80 w-full rounded-xl border border-line p-3 font-mono text-xs" /></label>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-gray-500">模块包含关系 JSON<textarea name="containment" defaultValue="[]"
            className="mt-1 min-h-20 w-full rounded-xl border border-line p-3 font-mono text-xs" /></label>
          <label className="text-xs text-gray-500">允许重叠关系 JSON<textarea name="allowed_overlaps" defaultValue="[]"
            className="mt-1 min-h-20 w-full rounded-xl border border-line p-3 font-mono text-xs" /></label>
          <input name="reviewer" required placeholder="设计负责人" className="rounded-xl border border-line px-3 py-2 text-sm" />
          <input name="reason" required placeholder="审核理由" className="rounded-xl border border-line px-3 py-2 text-sm" />
        </div>
        <button className="w-full rounded-xl bg-ink px-4 py-3 text-sm text-white">保存 Ground Truth</button>
        {message && <p className="text-sm">{message}</p>}
      </form></Card>
    </div>
  </div>;
}
