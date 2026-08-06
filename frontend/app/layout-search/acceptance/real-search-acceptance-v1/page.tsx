"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, RealSearchAcceptanceDataset, RealSearchAcceptanceResult } from "@/lib/api";
import { Card, Tag } from "@/components/ui";

const VERSION = "real-search-acceptance-v1";

function Result({ item, type, requirementId, reviewer, notes, save }: {
  item: RealSearchAcceptanceResult;
  type: "case" | "pattern";
  requirementId: number;
  reviewer: string;
  notes: string;
  save: (payload: { requirement_id: number; result_type: "case" | "pattern" | "none"; result_id: number; relevance: "relevant" | "irrelevant" | "uncertain"; reviewer: string; notes: string }) => Promise<void>;
}) {
  return <Card className="overflow-hidden">
    <div className="grid gap-4 md:grid-cols-[120px_1fr]">
      <div>{item.image_url ? <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={item.image_url} alt={item.name} className="h-28 w-28 rounded-xl object-cover" />
      </> : <div className="grid h-28 w-28 place-items-center rounded-xl bg-gray-100 text-xs text-gray-400">无预览图</div>}</div>
      <div>
        <div className="flex items-start justify-between gap-3"><div><div className="text-xs text-gray-400">#{item.rank} · {type === "case" ? "公司案例" : "正式模式"}</div><Link className="font-semibold text-accent" href={type === "case" ? `/cases/${item.id}` : `/patterns/${item.id}`}>{item.name}</Link></div><strong className="text-2xl text-accent">{item.total_score}</strong></div>
        <div className="mt-2 flex flex-wrap gap-2"><Tag>{item.product_category}</Tag>{item.content_purpose && <Tag>{item.content_purpose}</Tag>}{item.page_role && <Tag>{item.page_role}</Tag>}</div>
        <p className="mt-3 text-xs text-gray-600">{item.match_reasons.join("；")}</p>
        <details className="mt-3 text-xs text-gray-500"><summary className="cursor-pointer">来源证据</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap">{JSON.stringify(item.source_evidence, null, 2)}</pre></details>
        <div className="mt-4 grid grid-cols-3 gap-2"><button onClick={() => save({ requirement_id: requirementId, result_type: type, result_id: item.id, relevance: "relevant", reviewer, notes })} className="rounded-lg bg-emerald-600 px-2 py-2 text-xs text-white">合适</button><button onClick={() => save({ requirement_id: requirementId, result_type: type, result_id: item.id, relevance: "irrelevant", reviewer, notes })} className="rounded-lg border border-rose-200 px-2 py-2 text-xs text-rose-700">不合适</button><button onClick={() => save({ requirement_id: requirementId, result_type: type, result_id: item.id, relevance: "uncertain", reviewer, notes })} className="rounded-lg border px-2 py-2 text-xs">不确定</button></div>
      </div>
    </div>
  </Card>;
}

export default function RealSearchAcceptancePage() {
  const [data, setData] = useState<RealSearchAcceptanceDataset | null>(null);
  const [reviewer, setReviewer] = useState("张茗淇");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  const load = () => api.realSearchAcceptance(VERSION).then(setData).catch((error) => setMessage(error.message));
  useEffect(() => { void load(); }, []); // dataset version is fixed for this acceptance page
  async function save(payload: Parameters<typeof api.addRealSearchAcceptanceFeedback>[1]) {
    if (!reviewer.trim()) { setMessage("请填写审核人。"); return; }
    try { await api.addRealSearchAcceptanceFeedback(VERSION, payload); setMessage("人工判断已保存。"); await load(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
  }
  if (!data) return <p>{message || "加载中…"}</p>;
  return <div className="space-y-7">
    <header><div className="text-xs uppercase tracking-[.2em] text-accent">P3.2-F1</div><h1 className="mt-2 text-3xl font-bold">真实检索人工验收</h1><p className="mt-2 text-sm text-gray-500">只展示7条 Calibration。3条 Holdout 保持封存，页面不会读取其内容或结果。</p></header>
    <Card><div className="grid gap-3 text-sm md:grid-cols-5"><div>数据集<br/><b>{data.dataset_version}</b></div><div>进度<br/><b>{data.completed_count}/{data.calibration_count}</b></div><div>Holdout<br/><b>{data.holdout_count}条封存</b></div><div>已执行<br/><b>{data.holdout_executed ? "异常" : "否"}</b></div><div>已读取<br/><b>{data.holdout_read ? "异常" : "否"}</b></div></div></Card>
    <div className="grid gap-3 md:grid-cols-[1fr_2fr]"><input value={reviewer} onChange={(e) => setReviewer(e.target.value)} className="rounded-xl border border-line px-4 py-3 text-sm" placeholder="审核人（必填）"/><div className="rounded-xl bg-amber-50 p-3 text-sm">{message || "请判断推荐结果；系统不会自动生成正确答案。"}</div></div>
    {data.calibration.map((entry) => <section key={entry.requirement.id} className="space-y-4">
      <Card><div className="flex flex-wrap justify-between gap-3"><div><div className="text-xs text-gray-400">需求 #{entry.requirement.id}</div><Link href={`/requirements/${entry.requirement.id}`} className="text-xl font-semibold text-accent">{entry.requirement.title}</Link><p className="mt-2 whitespace-pre-wrap text-sm text-gray-600">{entry.requirement.raw_requirement}</p></div><div className="text-sm text-gray-500">案例 {entry.cases.length} · 模式 {entry.patterns.length}</div></div><textarea value={notes[entry.requirement.id] || ""} onChange={(e) => setNotes({...notes, [entry.requirement.id]: e.target.value})} className="mt-4 min-h-20 w-full rounded-xl border border-line p-3 text-sm" placeholder="判断原因（将随本次判断保存）"/><button onClick={() => save({ requirement_id: entry.requirement.id, result_type: "none", result_id: 0, relevance: "relevant", reviewer, notes: notes[entry.requirement.id] || "当前没有合适结果" })} className="mt-3 rounded-lg border border-amber-300 px-4 py-2 text-sm">当前没有合适结果</button>{entry.feedback.length > 0 && <p className="mt-3 text-xs text-emerald-700">已保存 {entry.feedback.length} 条人工判断</p>}</Card>
      <div><h2 className="mb-3 text-lg font-semibold">前10个公司案例</h2><div className="grid gap-4 xl:grid-cols-2">{entry.cases.map((item) => <Result key={item.id} item={item} type="case" requirementId={entry.requirement.id} reviewer={reviewer} notes={notes[entry.requirement.id] || ""} save={save}/>)}</div></div>
      <div><h2 className="mb-3 text-lg font-semibold">前3个正式排版模式</h2>{entry.patterns.length ? <div className="grid gap-4 xl:grid-cols-2">{entry.patterns.map((item) => <Result key={item.id} item={item} type="pattern" requirementId={entry.requirement.id} reviewer={reviewer} notes={notes[entry.requirement.id] || ""} save={save}/>)}</div> : <div className="rounded-xl bg-gray-50 p-5 text-sm text-gray-500">暂无合适公司模式；系统未跨品类强行推荐。</div>}</div>
    </section>)}
  </div>;
}
