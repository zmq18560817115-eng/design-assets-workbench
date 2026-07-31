"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, CaseOut } from "@/lib/api";
import { CaseCard, Card } from "@/components/ui";

type Tab = "library" | "import" | "review";
const sourceTypes = [
  ["company_published", "公司成品"],
  ["external_reference", "外部参考"],
  ["rejected_company_design", "未采用方案"],
  ["company_revision", "公司修订稿"],
];

export default function AssetsPage({
  searchParams,
}: {
  searchParams?: { tab?: string };
}) {
  const requested = searchParams?.tab;
  const [tab, setTab] = useState<Tab>(
    requested === "import" || requested === "review" ? requested : "library"
  );
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [message, setMessage] = useState("");
  const load = () => api.cases("", "", "layout").then(setCases).catch(() => setCases([]));
  useEffect(() => {
    void api.cases("", "", "layout").then(setCases).catch(() => setCases([]));
  }, []);
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!files.length) return setMessage("请选择图片");
    const data = new FormData(event.currentTarget);
    const meta = {
      uploader: String(data.get("uploader") || "anonymous"),
      source_type: String(data.get("source_type") || "external_reference"),
      product_category: String(data.get("product_category") || ""),
    };
    setMessage(`正在导入 ${files.length} 张素材…`);
    try {
      if (files.length === 1) {
        await api.analyze(files[0], meta);
      } else {
        const job = await api.analyzeBatch(files, meta);
        setMessage(`批量任务已创建：${job.batch_id}，共 ${job.total} 张`);
        return;
      }
      setMessage("素材已导入并进入待审核队列"); setFiles([]); load();
    } catch { setMessage("导入失败，请检查模型配置或稍后重试"); }
  };
  const visible = tab === "review"
    ? cases.filter((item) => item.trust_status === "ai_unverified")
    : cases;
  return <div className="space-y-7">
    <header><div className="text-xs font-semibold uppercase tracking-[.2em] text-accent">Asset center</div>
      <h1 className="mt-2 text-3xl font-semibold">素材中心</h1>
      <p className="mt-2 text-sm text-gray-500">统一管理素材、导入任务和待审核拆解。</p></header>
    <div className="flex gap-2 border-b border-line">
      {([["library","素材库"],["import","导入素材"],["review","待审核"]] as const).map(([value,label]) =>
        <button key={value} onClick={() => setTab(value)}
          className={`border-b-2 px-5 py-3 text-sm ${tab === value ? "border-accent text-accent" : "border-transparent text-gray-500"}`}>{label}</button>)}
    </div>
    {tab === "import" ? <Card>
      <form onSubmit={upload} className="grid gap-4 md:grid-cols-2">
        <label className="rounded-2xl border border-dashed border-line p-7 text-center text-sm md:col-span-2">
          <b>选择单张、多张或文件夹中的图片</b>
          <p className="mt-2 text-xs text-gray-500">Dry Run 和目录级 manifest 仍可使用后端导入脚本完成。</p>
          <input className="mt-4 block w-full text-xs" type="file" accept="image/*" multiple
            onChange={(e) => setFiles(Array.from(e.target.files || []))} />
        </label>
        <select name="source_type" className="rounded-xl border border-line px-3 py-2.5 text-sm">
          {sourceTypes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input name="product_category" placeholder="产品分类" className="rounded-xl border border-line px-3 py-2.5 text-sm" />
        <input name="uploader" placeholder="上传人" className="rounded-xl border border-line px-3 py-2.5 text-sm" />
        <input name="project_name" placeholder="项目信息（可选）" className="rounded-xl border border-line px-3 py-2.5 text-sm" />
        <button className="rounded-xl bg-ink px-5 py-3 text-sm text-white md:col-span-2">导入并分析 {files.length ? `(${files.length})` : ""}</button>
      </form>{message && <p className="mt-4 text-sm">{message}</p>}
    </Card> : <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {visible.map((item) => <CaseCard key={item.id} c={item} />)}
      {!visible.length && <Card className="sm:col-span-2">当前没有符合条件的素材。</Card>}
    </div>}
  </div>;
}
