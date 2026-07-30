"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { BusinessRequirementForm } from "@/components/business-requirement-form";
import { api, BusinessRequirement } from "@/lib/api";

export default function RequirementDetailPage() {
  const { id } = useParams<{id:string}>();
  const [item, setItem] = useState<BusinessRequirement | null>(null);
  const [message, setMessage] = useState("");
  useEffect(()=>{ api.businessRequirement(id).then(setItem).catch((e)=>setMessage(e.message)); },[id]);
  if (!item) return <p>{message || "加载中…"}</p>;
  return <div>
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div><h1 className="text-3xl font-bold">{item.title}</h1><p className="mt-2 text-sm text-gray-500">状态：{item.status} · 需求确认只锁定结构化条件，不生成排版方向。</p></div>
      <div className="flex gap-2">
        <Link href={`/requirements/${id}/layout-search`} className="rounded-xl bg-ink px-5 py-3 text-sm text-white">查找排版参考</Link>
        {item.status !== "confirmed" && <button className="rounded-xl bg-emerald-600 px-5 py-3 text-sm text-white" onClick={async()=>{try{setItem(await api.confirmBusinessRequirement(id));setMessage("需求已确认。");}catch(e){setMessage(e instanceof Error?e.message:"确认失败");}}}>确认需求</button>}
      </div>
    </div>
    {message && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}
    <BusinessRequirementForm key={item.updated_at} value={item} submitLabel="保存修改" disabled={item.status==="archived"} onSubmit={async(value)=>{try{const updated=await api.updateBusinessRequirement(id,value);setItem(updated);setMessage("修改已保存。");}catch(e){setMessage(e instanceof Error?e.message:"保存失败");}}} />
  </div>;
}
