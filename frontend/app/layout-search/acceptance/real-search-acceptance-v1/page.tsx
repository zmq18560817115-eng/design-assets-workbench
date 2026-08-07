"use client";

import { useEffect, useMemo, useState } from "react";
import { api, AcceptanceDecision, RealSearchAcceptanceDataset, RealSearchAcceptanceResult } from "@/lib/api";
import { Card, Tag } from "@/components/ui";

const VERSION = "real-search-acceptance-v1";
const STORAGE_KEY = `${VERSION}:human-review-draft:v2`;
const REVIEWER = "张茗淇";
type Choice = AcceptanceDecision["relevance"];
type Draft = Record<string, { relevance?: Choice; reasons: string[]; notes: string }>;

const labels: Record<Choice, string> = {
  relevant: "适合作为参考", irrelevant: "不适合作为参考", uncertain: "暂时无法判断",
};
const reasonOptions: Record<Choice, string[]> = {
  relevant: ["产品一致", "内容用途一致", "排版结构适合", "信息层级清楚", "可直接参考"],
  irrelevant: ["产品品类不一致", "内容用途不一致", "页面角色不一致", "排版结构不适合", "信息承载不足", "触犯禁止项"],
  uncertain: ["缺少业务信息", "图片看不清", "需要设计负责人判断"],
};
const suitable = new Set(["3:case:61", "3:case:66", "4:case:64", "9:case:361", "10:case:61", "10:case:63", "10:case:66"]);
const uncertain = new Set(["3:case:63", "3:case:64", "4:case:61", "4:case:63", "4:case:66", "9:case:371", "9:case:375", "9:case:363", "9:case:368", "10:case:64"]);

function keyOf(requirementId: number, type: "case" | "pattern" | "none", id: number) {
  return `${requirementId}:${type}:${id}`;
}
function suggestion(key: string) {
  if (suitable.has(key)) return { choice: "relevant" as Choice, reason: "业务主题与公司案例结构相符，可作为对应内容的参考。", issue: "仍需核对实际产品数量和 Brief 必需信息。" };
  if (uncertain.has(key)) return { choice: "uncertain" as Choice, reason: "部分结构可复用，但现有证据不足以直接判断适用。", issue: "请设计负责人重点检查信息容量、产品数量和页面角色。" };
  return { choice: "irrelevant" as Choice, reason: "推荐对象与需求的信息容量或页面角色不一致。", issue: "不建议仅因品类一致就采用。" };
}

function ChoiceButtons({ value, onChange }: { value?: Choice; onChange: (choice: Choice) => void }) {
  return <div className="grid gap-2 sm:grid-cols-3" role="group" aria-label="选择判断结果">
    {(Object.keys(labels) as Choice[]).map((choice) => <button key={choice} type="button" onClick={() => onChange(choice)}
      aria-pressed={value === choice}
      className={`min-h-12 rounded-xl border-2 px-3 py-2 text-base font-semibold ${value === choice ? "border-accent bg-accent text-white" : "border-line bg-white text-gray-800"}`}>
      {value === choice ? "✓ " : "○ "}{labels[choice]}
    </button>)}
  </div>;
}

function ResultCard({ item, type, requirementId, value, onChange, onZoom }: {
  item: RealSearchAcceptanceResult; type: "case" | "pattern"; requirementId: number;
  value: Draft[string]; onChange: (value: Draft[string]) => void; onZoom: (url: string, alt: string) => void;
}) {
  const key = keyOf(requirementId, type, item.id);
  const assist = suggestion(key);
  const selected = value.relevance;
  return <Card className="overflow-hidden border-2 border-line p-0">
    <div className="grid gap-5 p-5 lg:grid-cols-[minmax(260px,42%)_1fr]">
      <button type="button" className="group relative min-h-64 overflow-hidden rounded-2xl bg-gray-100" onClick={() => item.image_url && onZoom(item.image_url, item.name)}>
        {item.image_url ? <>{/* eslint-disable-next-line @next/next/no-img-element */}<img src={item.image_url} alt={item.name} className="h-full min-h-64 w-full object-cover"/><span className="absolute bottom-3 right-3 rounded-full bg-black/70 px-3 py-2 text-sm text-white">放大查看</span></> : <span className="text-gray-500">暂无案例图片</span>}
      </button>
      <div className="min-w-0 space-y-4">
        <div><div className="text-sm text-gray-500">{type === "case" ? `推荐案例 ${item.rank}` : `推荐排版方式 ${item.rank}`}</div><h3 className="mt-1 text-xl font-bold">{item.name}</h3></div>
        <div><div className="font-semibold">推荐原因</div><p className="mt-1 text-base text-gray-700">{item.match_reasons.join("；") || "同品类公司证据"}</p></div>
        <div className="rounded-xl bg-blue-50 p-4"><div className="font-semibold">系统辅助建议，仅供人工参考</div><p className="mt-1 text-base">{labels[assist.choice]}：{assist.reason}</p><p className="mt-2 text-base text-amber-800"><b>需要人工注意：</b>{assist.issue}</p></div>
        <ChoiceButtons value={selected} onChange={(choice) => onChange({ ...value, relevance: choice, reasons: [] })}/>
        {selected && <div><div className="mb-2 font-semibold">选择原因（可多选）</div><div className="flex flex-wrap gap-2">{reasonOptions[selected].map((reason) => <button key={reason} type="button" onClick={() => onChange({...value, reasons: value.reasons.includes(reason) ? value.reasons.filter((r) => r !== reason) : [...value.reasons, reason]})} className={`rounded-full border px-3 py-2 text-sm ${value.reasons.includes(reason) ? "border-accent bg-accent/10 font-semibold" : "border-line"}`}>{value.reasons.includes(reason) ? "✓ " : ""}{reason}</button>)}</div><input value={value.notes} onChange={(event) => onChange({...value, notes:event.target.value})} className="mt-3 w-full rounded-xl border border-line px-4 py-3 text-base" placeholder="可补充一句简短备注（选填）"/></div>}
        <details className="text-sm text-gray-500"><summary className="cursor-pointer font-medium">查看技术信息</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-3">{JSON.stringify({内部ID:item.id, 算法分数:item.total_score, 来源:item.source_evidence}, null, 2)}</pre></details>
      </div>
    </div>
  </Card>;
}

export default function RealSearchAcceptancePage() {
  const [data, setData] = useState<RealSearchAcceptanceDataset | null>(null);
  const [index, setIndex] = useState(0);
  const [draft, setDraft] = useState<Draft>({});
  const [message, setMessage] = useState("");
  const [zoom, setZoom] = useState<{url:string;alt:string}|null>(null);
  const [summary, setSummary] = useState(false);
  useEffect(() => { api.realSearchAcceptance(VERSION).then(setData).catch((error) => setMessage(error.message)); }, []);
  useEffect(() => { try { const saved = localStorage.getItem(STORAGE_KEY); if (saved) setDraft(JSON.parse(saved)); } catch {} }, []);
  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(draft)); }, [draft]);
  const expectedKeys = useMemo(() => data ? data.calibration.flatMap((entry) => entry.cases.length || entry.patterns.length ? [...entry.cases.map((item) => keyOf(entry.requirement.id,"case",item.id)), ...entry.patterns.map((item) => keyOf(entry.requirement.id,"pattern",item.id))] : [keyOf(entry.requirement.id,"none",0)]) : [], [data]);
  const completedRequirements = useMemo(() => data ? data.calibration.filter((entry) => {
    const keys = entry.cases.length || entry.patterns.length ? [...entry.cases.map((item) => keyOf(entry.requirement.id,"case",item.id)), ...entry.patterns.map((item) => keyOf(entry.requirement.id,"pattern",item.id))] : [keyOf(entry.requirement.id,"none",0)];
    return keys.every((key) => draft[key]?.relevance);
  }).length : 0, [data,draft]);
  const allComplete = expectedKeys.length > 0 && expectedKeys.every((key) => draft[key]?.relevance);
  const update = (key:string,value:Draft[string]) => setDraft((current) => ({...current,[key]:value}));
  const applySuggestions = () => {
    if (!data) return;
    const next = {...draft};
    data.calibration.forEach((entry) => [...entry.cases.map((item) => ["case",item] as const), ...entry.patterns.map((item) => ["pattern",item] as const)].forEach(([type,item]) => {
      const key = keyOf(entry.requirement.id,type,item.id); const assist = suggestion(key);
      if (assist.choice !== "uncertain") next[key] = {relevance:assist.choice,reasons:[],notes:""};
    }));
    setDraft(next); setMessage("已将明确建议应用到本机草稿；10条不确定项仍需人工查看，未写入正式结果。");
  };
  async function submit() {
    if (!data || !allComplete) return;
    if (!window.confirm("确认提交全部7条需求的正式验收结果吗？提交后不能在此页面部分覆盖。")) return;
    const decisions: AcceptanceDecision[] = expectedKeys.map((key) => { const [requirementId,type,resultId] = key.split(":"); const value=draft[key]; return {requirement_id:Number(requirementId),result_type:type as AcceptanceDecision["result_type"],result_id:Number(resultId),relevance:value.relevance!,reasons:value.reasons,notes:value.notes}; });
    try { const result=await api.submitRealSearchAcceptance(VERSION,{reviewer:REVIEWER,decisions}); setMessage(result.idempotent ? "正式验收结果已存在，本次没有重复写入。" : "正式验收结果已提交。"); }
    catch(error){setMessage(error instanceof Error?error.message:"提交失败");}
  }
  if (!data) return <p className="text-base">{message || "正在加载验收任务…"}</p>;
  const entry = data.calibration[index];
  const noResult = entry.cases.length === 0 && entry.patterns.length === 0;
  const noResultKey = keyOf(entry.requirement.id,"none",0);
  const counts = expectedKeys.reduce((acc,key) => { const choice=draft[key]?.relevance; if(choice && !key.includes(":none:")) acc[choice]++; return acc; },{relevant:0,irrelevant:0,uncertain:0} as Record<Choice,number>);
  return <div className="mx-auto max-w-7xl space-y-6 text-[16px]">
    <header><h1 className="text-3xl font-bold">真实需求推荐验收</h1><p className="mt-2 text-lg text-gray-600">共7条需求｜已完成{completedRequirements}条｜待判断{7-completedRequirements}条</p></header>
    <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-3 lg:sticky lg:top-5 lg:self-start"><Card><div className="mb-3 font-bold">7条验收任务</div>{data.calibration.map((item,i) => { const done=i<7 && (()=>{const e=data.calibration[i];const ks=e.cases.length||e.patterns.length?[...e.cases.map(x=>keyOf(e.requirement.id,"case",x.id)),...e.patterns.map(x=>keyOf(e.requirement.id,"pattern",x.id))]:[keyOf(e.requirement.id,"none",0)];return ks.every(k=>draft[k]?.relevance)})(); return <button type="button" key={item.requirement.id} onClick={()=>{setIndex(i);setSummary(false)}} className={`mb-2 w-full rounded-xl border p-3 text-left ${i===index&&!summary?"border-accent bg-accent/5":"border-line"}`}><span className="mr-2">{done?"✓":"○"}</span>任务{i+1}<span className="block truncate pl-6 text-sm text-gray-500">{item.requirement.title}</span></button>})}</Card><button type="button" onClick={applySuggestions} className="w-full rounded-xl border-2 border-accent px-4 py-3 font-semibold text-accent">将明确建议应用到草稿</button><button type="button" onClick={()=>setSummary(true)} className="w-full rounded-xl bg-gray-900 px-4 py-3 font-semibold text-white">查看最终汇总</button></aside>
      <main className="min-w-0 space-y-6">
        {message && <div className="rounded-xl bg-amber-50 p-4" role="status">{message}</div>}
        {summary ? <Card><h2 className="text-2xl font-bold">第四步：统一确认</h2><div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-emerald-50 p-4"><b>适合</b><div className="text-3xl font-bold">{counts.relevant}</div></div><div className="rounded-xl bg-rose-50 p-4"><b>不适合</b><div className="text-3xl font-bold">{counts.irrelevant}</div></div><div className="rounded-xl bg-amber-50 p-4"><b>不确定</b><div className="text-3xl font-bold">{counts.uncertain}</div></div></div><p className="mt-5">当前无合适结果的需求：{[1,5,6].filter((id)=>draft[keyOf(id,"none",0)]?.relevance).join("、")||"尚未确认"}</p><p className="mt-2">尚未判断：{expectedKeys.filter((key)=>!draft[key]?.relevance).length}项</p><p className="mt-2">审核人：<b>{REVIEWER}</b></p>{allComplete ? <button type="button" onClick={submit} className="mt-6 w-full rounded-xl bg-accent px-5 py-4 text-lg font-bold text-white">提交正式验收结果</button> : <div className="mt-6 rounded-xl bg-gray-100 p-4">全部必填判断完成后，才可提交正式验收结果。</div>}<details className="mt-5"><summary className="cursor-pointer">查看技术信息</summary><p className="mt-2 text-sm text-gray-500">数据集 {data.dataset_version}；封存任务未读取、未运行。</p></details></Card> : <>
          <Card><div className="text-sm font-semibold text-accent">第一步：看需求</div><div className="mt-4 grid gap-4 md:grid-cols-2"><div><span className="text-gray-500">产品品类</span><div className="text-xl font-bold">{entry.requirement.product_category}</div></div><div><span className="text-gray-500">需求标题</span><div className="text-xl font-bold">{entry.requirement.title}</div></div><div><span className="text-gray-500">内容用途</span><div>{entry.requirement.content_purpose||"待确认"}</div></div><div><span className="text-gray-500">页面角色</span><div>{entry.requirement.page_role||"待确认"}</div></div><div><span className="text-gray-500">必须展示内容</span><div className="mt-1 flex flex-wrap gap-2">{entry.requirement.required_modules_json.length?entry.requirement.required_modules_json.map(x=><Tag key={x}>{x}</Tag>):"Brief未单独列出"}</div></div><div><span className="text-gray-500">禁止出现内容</span><div className="mt-1 flex flex-wrap gap-2">{entry.requirement.forbidden_modules_json.length?entry.requirement.forbidden_modules_json.map(x=><Tag key={x}>{x}</Tag>):"Brief未单独列出"}</div></div></div><details className="mt-5"><summary className="cursor-pointer font-semibold">查看原始Brief</summary><p className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-4 text-sm">{entry.requirement.raw_requirement}</p></details></Card>
          {noResult ? <Card><div className="text-sm font-semibold text-accent">第二步：看系统推荐</div><div className="py-12 text-center"><div className="text-5xl">○</div><h2 className="mt-4 text-2xl font-bold">当前公司素材库中，暂无符合该品类需求的案例和排版模式。</h2><button type="button" onClick={()=>update(noResultKey,{relevance:"relevant",reasons:["当前没有合适结果"],notes:""})} className={`mt-6 rounded-xl px-6 py-4 text-lg font-bold ${draft[noResultKey]?.relevance?"bg-accent text-white":"border-2 border-accent text-accent"}`}>{draft[noResultKey]?.relevance?"✓ 已确认目前没有合适结果":"确认目前没有合适结果"}</button></div></Card> : <><section><div className="mb-3"><div className="text-sm font-semibold text-accent">第二步：看系统推荐</div><h2 className="text-2xl font-bold">推荐案例</h2></div><div className="space-y-5">{entry.cases.map(item=><ResultCard key={item.id} item={item} type="case" requirementId={entry.requirement.id} value={draft[keyOf(entry.requirement.id,"case",item.id)]||{reasons:[],notes:""}} onChange={value=>update(keyOf(entry.requirement.id,"case",item.id),value)} onZoom={(url,alt)=>setZoom({url,alt})}/>)}</div></section><section><h2 className="mb-3 text-2xl font-bold">推荐排版方式</h2><div className="space-y-5">{entry.patterns.map(item=><ResultCard key={item.id} item={item} type="pattern" requirementId={entry.requirement.id} value={draft[keyOf(entry.requirement.id,"pattern",item.id)]||{reasons:[],notes:""}} onChange={value=>update(keyOf(entry.requirement.id,"pattern",item.id),value)} onZoom={(url,alt)=>setZoom({url,alt})}/>)}</div></section></>}
          <div className="sticky bottom-3 z-10 flex items-center justify-between rounded-2xl border bg-white/95 p-3 shadow-lg"><button type="button" disabled={index===0} onClick={()=>setIndex(index-1)} className="rounded-xl border px-5 py-3 disabled:opacity-40">上一条</button><span>任务 {index+1}/7</span><button type="button" disabled={index===6} onClick={()=>setIndex(index+1)} className="rounded-xl bg-gray-900 px-5 py-3 text-white disabled:opacity-40">下一条</button></div>
        </>}
      </main>
    </div>
    {zoom && <div className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-5" role="dialog" aria-modal="true" aria-label="案例大图"><button type="button" onClick={()=>setZoom(null)} className="absolute right-5 top-5 rounded-full bg-white px-4 py-3 font-bold">关闭大图</button>{/* eslint-disable-next-line @next/next/no-img-element */}<img src={zoom.url} alt={zoom.alt} className="max-h-[88vh] max-w-[94vw] rounded-xl object-contain"/></div>}
  </div>;
}
