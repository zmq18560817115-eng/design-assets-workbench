"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Candidate = { relativePath: string; imageUrl: string; filename: string };
type ReviewItem = {
  id: string; category: string; originalPath: string; annotationPath: string;
  originalImageUrl: string; annotationImageUrl: string; originalFilename: string;
  annotationFilename: string; pairingStatus: "candidate_match" | "ambiguous";
  basis: string; similarity: string; problem: string; humanDecision: string;
  reviewer: string; reviewNotes: string; selectedOriginal: string; candidates: Candidate[];
};
type Payload = { items: ReviewItem[]; total: number; completed: number; counts: Record<string, number> };

const decisions = [
  ["confirmed", "配对正确", "bg-emerald-600 hover:bg-emerald-700"],
  ["rejected", "配对错误", "bg-red-600 hover:bg-red-700"],
  ["duplicate_excluded", "重复图片", "bg-amber-600 hover:bg-amber-700"],
  ["missing_original", "缺少原图", "bg-slate-700 hover:bg-slate-800"],
  ["missing_annotation", "缺少彩框图", "bg-slate-700 hover:bg-slate-800"],
] as const;

export default function PairingReviewPage() {
  const [data, setData] = useState<Payload>({ items: [], total: 0, completed: 0, counts: {} });
  const [selectedId, setSelectedId] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [selectedOriginal, setSelectedOriginal] = useState("");
  const [notice, setNotice] = useState("");
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch("/api/pairing-review", { cache: "no-store" });
    if (!response.ok) throw new Error(await response.text());
    const next = await response.json() as Payload;
    setData(next);
    setSelectedId((current) => current && next.items.some((item) => item.id === current) ? current : (next.items[0]?.id ?? ""));
  }, []);
  useEffect(() => { void load().catch((error) => setNotice(String(error))); }, [load]);

  const selected = useMemo(() => data.items.find((item) => item.id === selectedId), [data.items, selectedId]);
  useEffect(() => {
    if (!selected) return;
    setReviewer(selected.reviewer || reviewer);
    setSelectedOriginal(selected.pairingStatus === "ambiguous" ? selected.selectedOriginal : selected.originalPath);
    setNotice("");
    // reviewer intentionally persists while moving through the queue.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function save(decision: string) {
    if (!selected || !reviewer.trim()) { setNotice("请先填写审核人姓名。 "); return; }
    if (decision === "confirmed" && selected.pairingStatus === "ambiguous" && !selectedOriginal) { setNotice("该记录有多个候选，请先人工选择一张原图。 "); return; }
    setSaving(true);
    const response = await fetch("/api/pairing-review", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected.id, decision, reviewer, selectedOriginal }),
    });
    const result = await response.json();
    if (!response.ok) setNotice(result.detail ?? "保存失败");
    else { setNotice("审核结果已保存到本地清单。 "); await load(); }
    setSaving(false);
  }

  const progress = data.total ? Math.round(data.completed / data.total * 100) : 0;
  return (
    <main className="space-y-6 pb-12">
      <header className="rounded-3xl bg-gradient-to-r from-slate-950 to-indigo-950 p-7 text-white shadow-xl">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div><p className="mb-2 text-xs font-semibold tracking-[0.24em] text-indigo-200">公司成品 · 彩框标注</p><h1 className="text-3xl font-bold">图片配对人工审核</h1><p className="mt-2 text-sm text-slate-300">只保存配对判断，不写数据库，不产生 verified。</p></div>
          <div className="min-w-64"><div className="mb-2 flex justify-between text-sm"><span>审核进度</span><strong>{data.completed} / {data.total}（{progress}%）</strong></div><div className="h-2 overflow-hidden rounded-full bg-white/20"><div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${progress}%` }} /></div><p className="mt-2 text-xs text-slate-300">候选 {data.counts.candidate_match ?? 0} · 多候选 {data.counts.ambiguous ?? 0}</p></div>
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="max-h-[74vh] overflow-y-auto rounded-2xl border border-line bg-white p-2 shadow-sm">
          {data.items.map((item, index) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`mb-1 w-full rounded-xl px-3 py-3 text-left transition ${selectedId === item.id ? "bg-indigo-600 text-white" : "hover:bg-indigo-50"}`}><div className="flex items-center justify-between"><strong className="text-sm">{index + 1}. {item.category}</strong><span className={`h-2.5 w-2.5 rounded-full ${item.humanDecision ? "bg-emerald-400" : "bg-amber-400"}`} /></div><p className={`mt-1 truncate text-xs ${selectedId === item.id ? "text-indigo-100" : "text-gray-500"}`}>{item.annotationFilename}</p><p className="mt-1 text-[11px]">{item.pairingStatus === "ambiguous" ? "多个候选，需选择" : "单一候选"}</p></button>)}
        </aside>

        {selected ? <section className="space-y-5">
          <div className="rounded-2xl border border-line bg-white p-5 shadow-sm"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">{selected.category}</span><span className="ml-2 rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-700">{selected.pairingStatus}</span></div><div className="text-xs text-gray-500">相似度 {selected.similarity || "—"}</div></div>
            <div className="grid gap-5 md:grid-cols-2">
              <div><h2 className="mb-2 font-semibold">公司成品原图</h2>{selected.pairingStatus === "ambiguous" ? <div className="grid grid-cols-2 gap-3">{selected.candidates.map((candidate) => <button key={candidate.relativePath} onClick={() => setSelectedOriginal(candidate.relativePath)} className={`overflow-hidden rounded-xl border-2 p-2 text-left transition ${selectedOriginal === candidate.relativePath ? "border-indigo-600 bg-indigo-50" : "border-gray-200 hover:border-indigo-300"}`}><img src={candidate.imageUrl} alt={candidate.filename} onDoubleClick={() => setZoom({ src: candidate.imageUrl, alt: candidate.filename })} className="h-56 w-full rounded-lg bg-gray-50 object-contain" /><p className="mt-2 break-all text-xs">{candidate.filename}</p><p className="mt-1 text-xs font-semibold text-indigo-700">{selectedOriginal === candidate.relativePath ? "已人工选择" : "点击选择"}</p></button>)}</div> : <button onClick={() => setZoom({ src: selected.originalImageUrl, alt: selected.originalFilename })} className="w-full overflow-hidden rounded-xl border bg-gray-50"><img src={selected.originalImageUrl} alt={selected.originalFilename} className="h-[440px] w-full object-contain" /></button>}<p className="mt-2 break-all text-xs text-gray-500">{selectedOriginal || selected.originalFilename}</p></div>
              <div><h2 className="mb-2 font-semibold">彩框标注图</h2><button onClick={() => setZoom({ src: selected.annotationImageUrl, alt: selected.annotationFilename })} className="w-full overflow-hidden rounded-xl border bg-gray-50"><img src={selected.annotationImageUrl} alt={selected.annotationFilename} className="h-[440px] w-full object-contain" /></button><p className="mt-2 break-all text-xs text-gray-500">{selected.annotationFilename}</p></div>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-5 shadow-sm"><label className="block text-sm font-semibold">审核人</label><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="请输入真实姓名或固定审核代号" className="mt-2 w-full rounded-xl border border-gray-300 px-4 py-3 outline-none focus:border-indigo-500" /><p className="mt-3 rounded-xl bg-gray-50 p-3 text-xs leading-5 text-gray-600">检测依据：{selected.basis}<br />问题说明：{selected.problem || "无"}</p><div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">{decisions.map(([value, label, color]) => <button key={value} disabled={saving} onClick={() => void save(value)} className={`rounded-xl px-3 py-3 text-sm font-semibold text-white disabled:opacity-50 ${color}`}>{label}</button>)}</div>{notice && <p role="status" className="mt-3 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-800">{notice}</p>}{selected.humanDecision && <p className="mt-3 text-sm text-emerald-700">已保存：{selected.humanDecision} · {selected.reviewNotes}</p>}</div>
        </section> : <div className="rounded-2xl border bg-white p-10 text-center text-gray-500">正在读取待审核清单……</div>}
      </div>

      {zoom && <div role="dialog" aria-modal="true" onClick={() => setZoom(null)} className="fixed inset-0 z-50 grid cursor-zoom-out place-items-center bg-black/80 p-8"><button className="absolute right-6 top-6 rounded-full bg-white px-4 py-2 text-sm">关闭</button><img src={zoom.src} alt={zoom.alt} className="max-h-full max-w-full rounded-xl object-contain shadow-2xl" /></div>}
    </main>
  );
}
