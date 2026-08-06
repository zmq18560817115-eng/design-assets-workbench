"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BusinessRequirementForm } from "@/components/business-requirement-form";
import { api, BusinessRequirement } from "@/lib/api";

const required: Array<[keyof BusinessRequirement, string]> = [
  ["title", "标题"], ["raw_requirement", "原始需求"], ["project_id", "项目"],
  ["product_category", "产品品类"], ["product_name", "产品名称"], ["channel", "渠道"],
  ["content_purpose", "内容用途"], ["page_role", "页面角色"], ["canvas_ratio", "画布比例"],
  ["brief_source", "真实Brief来源"], ["reviewer", "审核人"],
];

export default function RequirementDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<BusinessRequirement | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => { api.businessRequirement(id).then(setItem).catch((e) => setMessage(e.message)); }, [id]);
  const missing = useMemo(() => item ? required.filter(([key]) => !item[key]).map(([, label]) => label) : [], [item]);
  if (!item) return <p>{message || "加载中…"}</p>;
  const label = item.status === "confirmed" ? "已确认" : missing.length ? "待补充" : "草稿";
  return <div>
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div><h1 className="text-3xl font-bold">{item.title}</h1><p className="mt-2 text-sm text-gray-500">状态：{label} · 审核人：{item.reviewer || "未填写"}</p>{missing.length > 0 && <p className="mt-1 text-sm text-amber-700">缺少：{missing.join("、")}</p>}</div>
      <div className="flex gap-2"><Link href={`/requirements/${id}/layout-search`} className="rounded-xl bg-ink px-5 py-3 text-sm text-white">查找排版参考</Link>{item.status !== "confirmed" && <button disabled={missing.length > 0} className="rounded-xl bg-emerald-600 px-5 py-3 text-sm text-white disabled:opacity-40" onClick={async () => { try { setItem(await api.confirmBusinessRequirement(id, item.reviewer || "")); setMessage("需求已确认。"); } catch (e) { setMessage(e instanceof Error ? e.message : "确认失败"); } }}>确认需求</button>}</div>
    </div>
    {message && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}
    <BusinessRequirementForm key={item.updated_at} value={item} submitLabel="保存修改" disabled={item.status === "archived"} onSubmit={async (value) => { try { const updated = await api.updateBusinessRequirement(id, value); setItem(updated); setMessage("修改已保存。"); } catch (e) { setMessage(e instanceof Error ? e.message : "保存失败"); } }} />
  </div>;
}
