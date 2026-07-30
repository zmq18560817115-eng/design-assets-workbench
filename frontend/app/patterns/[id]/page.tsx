"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutWireframe } from "@/components/layout-wireframe";
import { Card, Tag } from "@/components/ui";
import {
  api,
  LayoutPattern,
  LayoutPatternEvidence,
} from "@/lib/api";

export default function PatternDetailPage() {
  const { id } = useParams<{id:string}>();
  const [item, setItem] = useState<LayoutPattern|null>(null);
  const [evidence, setEvidence] = useState<LayoutPatternEvidence|null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [suitable, setSuitable] = useState("");
  const [unsuitable, setUnsuitable] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.layoutPattern(id).then(value => {
      setItem(value); setName(value.name); setDescription(value.description);
      setSuitable(value.suitable_scenes_json.join("、"));
      setUnsuitable(value.unsuitable_scenes_json.join("、"));
    }).catch(error => setMessage(error.message));
    api.layoutPatternEvidence(id).then(setEvidence).catch(error => setMessage(error.message));
  }, [id]);

  if (!item) return <p>{message || "加载中…"}</p>;
  const split = (value:string) => value.split(/[、,，\n]/).map(v=>v.trim()).filter(Boolean);
  async function save() {
    try {
      setItem(await api.updateLayoutPattern(item!.id, {
        name, description,
        suitable_scenes_json: split(suitable),
        unsuitable_scenes_json: split(unsuitable),
        reviewer: "设计负责人",
      }));
      setMessage("模式信息已保存。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
  }

  return <div>
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><div className="text-xs uppercase tracking-[.2em] text-accent">Pattern evidence</div><h1 className="mt-2 text-3xl font-bold">{item.name}</h1><p className="mt-2 text-sm text-gray-500">{item.pattern_code || "旧人工模式"} · v{item.version} · {item.discovery_method || "manual"}</p></div>
      <div className="flex gap-2">
        {!["verified","disabled"].includes(item.review_status) && <button onClick={async()=>{try{setItem(await api.verifyLayoutPattern(item.id,"设计负责人"));setMessage("模式已确认。");}catch(error){setMessage(error instanceof Error?error.message:"确认失败");}}} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm text-white">人工确认</button>}
        {item.review_status !== "disabled" && <button onClick={async()=>{try{setItem(await api.disableLayoutPattern(item.id,"设计负责人"));setMessage("模式已停用，历史数据仍保留。");}catch(error){setMessage(error instanceof Error?error.message:"停用失败");}}} className="rounded-xl border border-rose-200 px-4 py-2 text-sm text-rose-600">停用模式</button>}
      </div>
    </div>
    {message && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}

    <div className="mt-7 grid gap-6 lg:grid-cols-[.8fr_1.2fr]">
      <Card><LayoutWireframe blueprint={item} showLabels showFocalRegion /><div className="mt-4 flex flex-wrap gap-2"><Tag>{item.canvas_ratio}</Tag><Tag>{item.orientation}</Tag><Tag>{item.information_density}</Tag><Tag>{item.reading_flow || "未标阅读动线"}</Tag><Tag>{item.review_status === "human_edited" ? "draft" : item.review_status}</Tag></div></Card>
      <Card><div className="grid gap-4"><label className="text-sm">模式名称<input value={name} onChange={e=>setName(e.target.value)} className="mt-1 w-full rounded-xl border border-line p-3"/></label><label className="text-sm">模式说明<textarea value={description} onChange={e=>setDescription(e.target.value)} className="mt-1 min-h-24 w-full rounded-xl border border-line p-3"/></label><label className="text-sm">适用场景<input value={suitable} onChange={e=>setSuitable(e.target.value)} className="mt-1 w-full rounded-xl border border-line p-3"/></label><label className="text-sm">不适用场景<input value={unsuitable} onChange={e=>setUnsuitable(e.target.value)} className="mt-1 w-full rounded-xl border border-line p-3"/></label><button onClick={save} disabled={item.review_status==="disabled"} className="rounded-xl bg-ink px-5 py-3 text-sm text-white disabled:opacity-40">保存修改</button></div></Card>
    </div>

    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <Card><h2 className="font-semibold">标准模块</h2><div className="mt-3"><div className="text-xs text-gray-400">必需模块（≥80%）</div><div className="mt-2 flex flex-wrap gap-2">{item.required_modules_json.map(value=><Tag key={value}>{value}</Tag>)}</div></div><div className="mt-4"><div className="text-xs text-gray-400">可选模块（30%～79%）</div><div className="mt-2 flex flex-wrap gap-2">{item.optional_modules_json.map(value=><Tag key={value}>{value}</Tag>)}</div></div></Card>
      <Card><h2 className="font-semibold">模式证据</h2><div className="mt-3 flex flex-wrap gap-2"><Tag>不同案例 {item.evidence_count}</Tag><Tag>{item.confidence_level}</Tag><Tag>蓝图 {item.evidence_blueprint_ids_json.length}</Tag></div><p className="mt-3 text-xs text-gray-500">生成时间：{item.generated_at ? new Date(item.generated_at).toLocaleString() : "旧模式无自动生成时间"}</p></Card>
    </div>
    <Card className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">业务适用知识</h2>
          <p className="mt-1 text-xs text-gray-500">由证据案例聚合生成；人工确认后重建不会覆盖，证据变化会标记 stale。</p>
        </div>
        <div className="flex items-center gap-2">
          <Tag>{item.business_context_review_status}</Tag>
          {item.business_context_review_status !== "verified" && <button className="rounded-xl bg-emerald-600 px-4 py-2 text-sm text-white" onClick={async () => {
            try {
              setItem(await api.updateLayoutPattern(item.id, {
                business_context_review_status: "verified",
                reviewer: "设计负责人",
              }));
              setMessage("业务适用知识已人工确认。");
            } catch (error) {
              setMessage(error instanceof Error ? error.message : "确认失败");
            }
          }}>确认业务适用性</button>}
        </div>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <div><div className="text-xs text-gray-400">产品类别</div><div className="mt-2 flex flex-wrap gap-2">{item.product_category_tags_json.map(value => <Tag key={value}>{value}</Tag>)}</div></div>
        <div><div className="text-xs text-gray-400">内容目的</div><div className="mt-2 flex flex-wrap gap-2">{item.content_purpose_tags_json.map(value => <Tag key={value}>{value}</Tag>)}</div></div>
        <div><div className="text-xs text-gray-400">活动阶段</div><div className="mt-2 flex flex-wrap gap-2">{item.campaign_stage_tags_json.map(value => <Tag key={value}>{value}</Tag>)}</div></div>
      </div>
    </Card>

    <Card className="mt-6"><h2 className="font-semibold">来源案例与相似度</h2><div className="mt-4 grid gap-3">{evidence?.similarities.map(row=><div key={row.blueprint_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3 text-sm"><div><Link href={`/cases/${row.case_id}`} className="font-medium text-accent">案例 #{row.case_id}</Link><span className="ml-3 text-xs text-gray-400">蓝图 #{row.blueprint_id}</span></div><div className="flex gap-3 text-xs"><span>总相似度 {(row.similarity.total*100).toFixed(1)}%</span><span>模块 {(row.similarity.module_types*100).toFixed(0)}%</span><span>位置 {(row.similarity.position_size*100).toFixed(0)}%</span></div></div>)}</div></Card>

    <Card className="mt-6"><h2 className="font-semibold">平均模块位置</h2><div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="text-gray-400"><th className="pb-2">模块</th><th>x</th><th>y</th><th>width</th><th>height</th><th>出现率</th></tr></thead><tbody>{item.average_positions_json.map(module=><tr key={module.id} className="border-t border-line"><td className="py-2">{module.id}</td><td>{module.x}</td><td>{module.y}</td><td>{module.width}</td><td>{module.height}</td><td>{Math.round(module.confidence*100)}%</td></tr>)}</tbody></table></div><div className="mt-4 text-xs text-gray-500">参与归纳：{evidence?.participating_modules.join("、") || "无"}<br/>排除模块：{evidence?.excluded_modules.join("、") || "无"}</div></Card>
  </div>;
}
