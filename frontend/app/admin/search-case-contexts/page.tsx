"use client";

import { api, SearchCaseContext } from "@/lib/api";
import { useEffect, useMemo, useState } from "react";

const purposes = ["产品介绍", "卖点说明", "参数对比", "上新宣传", "活动促销", "品牌表达", "使用教程", "用户教育"];
const channels = ["小红书", "电商详情", "产品海报", "社交媒体", "活动宣传", "内部提案", "其他"];
const roles = ["封面", "详情页首屏", "卖点页", "参数页", "教程页", "总结页", "其他"];

export default function SearchCaseContextsPage() {
  const [items, setItems] = useState<SearchCaseContext[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [missing, setMissing] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [contentPurpose, setContentPurpose] = useState("");
  const [channel, setChannel] = useState("");
  const [pageRole, setPageRole] = useState("");
  const [message, setMessage] = useState("");
  const load = () => api.searchCaseContexts().then((r) => setItems(r.items)).catch((e) => setMessage(e.message));
  useEffect(() => { void load(); }, []);
  const filtered = useMemo(() => items.filter((item) =>
    (!category || item.product_category === category) &&
    (!status || item.confirmation_status === status) &&
    (!missing || item.missing_fields.includes(missing))
  ), [items, category, status, missing]);
  const values = Object.fromEntries(Object.entries({ content_purpose: contentPurpose, channel, page_role: pageRole }).filter(([, v]) => v));
  async function save(verify: boolean) {
    if (!reviewer.trim()) return setMessage("批量操作必须填写审核人。");
    if (!selected.length) return setMessage("请先选择案例。");
    if (!verify && !Object.keys(values).length) return setMessage("请至少填写一个业务字段。");
    if (!window.confirm(`将影响 ${selected.length} 个案例，是否继续？`)) return;
    try {
      const result = await api.updateSearchCaseContexts({ case_ids: selected, values, reviewer, verify });
      setMessage(`已处理 ${result.affected_count} 个案例。`); setSelected([]); load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "操作失败"); }
  }
  return <div className="space-y-6">
    <div><div className="text-xs uppercase tracking-[.2em] text-gray-400">Search case contexts</div><h1 className="mt-2 text-3xl font-bold">检索案例业务上下文</h1><p className="mt-2 text-sm text-gray-500">仅显示当前92个目标案例；AI建议不会自动成为正式字段。</p></div>
    <section className="rounded-2xl border border-line bg-white p-5">
      <div className="grid gap-3 md:grid-cols-4">
        <Filter value={category} setValue={setCategory} label="品类" options={[...new Set(items.map((i) => i.product_category))]} />
        <Filter value={status} setValue={setStatus} label="状态" options={["draft", "verified"]} />
        <Filter value={missing} setValue={setMissing} label="缺失字段" options={["product_category", "content_purpose", "channel", "page_role"]} />
        <label className="text-sm">审核人<input className="field" value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></label>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3"><Filter value={contentPurpose} setValue={setContentPurpose} label="内容用途" options={purposes} /><Filter value={channel} setValue={setChannel} label="渠道" options={channels} /><Filter value={pageRole} setValue={setPageRole} label="页面角色" options={roles} /></div>
      <div className="mt-4 flex gap-2"><button className="rounded-xl bg-ink px-4 py-2 text-sm text-white" onClick={() => save(false)}>批量填写（{selected.length}）</button><button className="rounded-xl bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-40" disabled={!reviewer || !selected.length} onClick={() => save(true)}>负责人确认</button></div>
      {message && <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{message}</p>}
    </section>
    <div className="text-sm text-gray-500">当前显示 {filtered.length} / {items.length}，已选择 {selected.length}</div>
    <div className="space-y-3">{filtered.map((item) => <article key={item.case_id} className="rounded-2xl border border-line bg-white p-5"><div className="flex gap-4">
      <input type="checkbox" checked={selected.includes(item.case_id)} onChange={(e) => setSelected((current) => e.target.checked ? [...current, item.case_id] : current.filter((id) => id !== item.case_id))} />
      {item.image_url && <img src={item.image_url} alt="案例原图" className="h-24 w-24 rounded-lg object-cover" />}
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><strong>Case {item.case_id} · {item.case_name}</strong><Badge>{item.product_category}</Badge><Badge>{item.confirmation_status}</Badge>{item.evidence_strength === "weak" && <span className="rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-800">弱证据</span>}</div>
        <p className="mt-2 text-sm">正式字段：用途 {item.content_purpose || "待填写"} · 渠道 {item.channel || "待填写"} · 页面角色 {item.page_role || "待填写"}</p>
        <p className="mt-1 text-xs text-gray-500">缺少：{item.missing_fields.join("、") || "无"} · 正式模式 {item.pattern_ids.join(", ") || "—"}</p>
        <details className="mt-3 text-xs"><summary className="cursor-pointer">查看技术来源、AI建议和审核历史</summary><pre className="mt-2 overflow-auto rounded-lg bg-gray-50 p-3">{JSON.stringify({ field_sources: item.field_sources, suggestions: item.suggestions, annotation_id: item.annotation_id, blueprint_id: item.blueprint_id, history: item.history }, null, 2)}</pre></details>
      </div></div></article>)}</div>
  </div>;
}

function Filter({ value, setValue, label, options }: { value: string; setValue: (v: string) => void; label: string; options: string[] }) { return <label className="text-sm">{label}<select className="field" value={value} onChange={(e) => setValue(e.target.value)}><option value="">全部/请选择</option>{options.filter(Boolean).map((o) => <option key={o}>{o}</option>)}</select></label>; }
function Badge({ children }: { children: React.ReactNode }) { return <span className="rounded-full bg-gray-100 px-2 py-1 text-xs">{children}</span>; }
