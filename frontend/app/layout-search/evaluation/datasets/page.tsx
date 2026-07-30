"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { api, LayoutSearchDataset } from "@/lib/api";

export default function DatasetListPage() {
  const [items, setItems] = useState<LayoutSearchDataset[]>([]);
  const [version, setVersion] = useState("");
  const [name, setName] = useState("");
  const [creator, setCreator] = useState("");
  const [message, setMessage] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [validatedFileName, setValidatedFileName] = useState("");
  const load = () => api.layoutSearchDatasets().then(setItems).catch((e) => setMessage(e.message));
  useEffect(() => { load(); }, []);

  async function create() {
    try {
      await api.createLayoutSearchDataset({
        dataset_version: version, name, description: "",
        dataset_kind: "real", created_by: creator,
      });
      setVersion(""); setName(""); setMessage("真实验收数据集已创建。");
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "创建失败"); }
  }
  async function inspectImport(execute = false) {
    if (!pendingFile) return;
    if (execute && !window.confirm("确认导入已通过 dry-run 的冻结验收包？该版本导入后不可修改。")) return;
    try {
      const result = await api.importLayoutSearchEvaluation(pendingFile, execute);
      if (!execute) setValidatedFileName(pendingFile.name);
      setMessage(`${result.dry_run ? "dry-run 校验通过" : "导入完成"}：${result.dataset_version}，${result.annotation_count} 条标注`);
      if (execute) await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "导入失败"); }
  }
  return <div className="space-y-6">
    <div><div className="text-xs uppercase tracking-[.2em] text-accent">Ground Truth workspace</div><h1 className="mt-2 text-3xl font-bold">验收数据集</h1><p className="mt-2 text-sm text-gray-500">创建、标注、冻结并运行真实业务验收。fixture 只能验证工具链。</p></div>
    {message && <div className="rounded-xl bg-lilac p-3 text-sm">{message}</div>}
    <Card>
      <h2 className="font-semibold">创建数据集版本</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <input className="rounded-xl border border-line p-3 text-sm" placeholder="版本，如 real-2026-08-v1" value={version} onChange={(e) => setVersion(e.target.value)} />
        <input className="rounded-xl border border-line p-3 text-sm" placeholder="名称" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="rounded-xl border border-line p-3 text-sm" placeholder="创建人" value={creator} onChange={(e) => setCreator(e.target.value)} />
        <button className="rounded-xl bg-ink px-4 py-3 text-sm text-white" onClick={create}>创建真实数据集</button>
      </div>
    </Card>
    <Card>
      <h2 className="font-semibold">导入完整验收 JSON</h2>
      <p className="mt-1 text-xs text-gray-500">默认只做 dry-run；校验时间、枚举、ID、冻结状态和版本冲突，不写数据库。</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <input type="file" accept=".json,application/json" onChange={(e) => { setPendingFile(e.target.files?.[0] || null); setValidatedFileName(""); }} />
        <button className="rounded-xl border border-line px-4 py-2 text-sm" onClick={() => inspectImport(false)}>dry-run 校验</button>
        <button disabled={!pendingFile || validatedFileName !== pendingFile.name} className="rounded-xl bg-amber-600 px-4 py-2 text-sm text-white disabled:opacity-40" onClick={() => inspectImport(true)}>确认导入</button>
      </div>
    </Card>
    <div className="grid gap-4">
      {items.map((item) => <Link key={item.dataset_version} href={`/layout-search/evaluation/datasets/${encodeURIComponent(item.dataset_version)}`}>
        <Card className="transition hover:border-accent/40">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><div className="font-semibold">{item.name}</div><div className="mt-1 text-xs text-gray-500">{item.dataset_version} · {item.dataset_kind}</div></div>
            <span className={`rounded-full px-3 py-1 text-xs ${item.frozen_at ? "bg-slate-100" : "bg-amber-100 text-amber-700"}`}>{item.frozen_at ? "已冻结" : "编辑中"}</span>
          </div>
          <div className="mt-4 grid gap-2 text-sm md:grid-cols-4"><span>不同需求 {item.requirement_count}</span><span>标注 {item.annotation_count}</span><span>calibration {item.calibration_requirement_count}</span><span>holdout {item.holdout_requirement_count}</span></div>
        </Card>
      </Link>)}
    </div>
  </div>;
}
