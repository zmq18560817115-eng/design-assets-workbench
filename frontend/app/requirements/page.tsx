"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BusinessRequirement } from "@/lib/api";

export default function RequirementsPage() {
  const [items, setItems] = useState<BusinessRequirement[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api.businessRequirements().then(setItems).catch((e)=>setError(e.message)); }, []);
  return <div>
    <div className="flex items-end justify-between">
      <div><div className="text-xs uppercase tracking-[.2em] text-gray-400">Business requirements</div><h1 className="mt-2 text-3xl font-bold">业务需求</h1></div>
      <Link href="/requirements/new" className="rounded-xl bg-ink px-5 py-3 text-sm text-white">创建需求</Link>
    </div>
    {error && <p className="mt-5 text-red-500">{error}</p>}
    <div className="mt-6 space-y-3">{items.map((item)=>
      <Link key={item.id} href={`/requirements/${item.id}`} className="block rounded-2xl border border-line bg-white p-5 hover:border-accent">
        <div className="flex justify-between gap-4"><div><div className="font-semibold">{item.title}</div><div className="mt-2 text-sm text-gray-500">{item.product_category || "未填品类"} · {item.channel || "未填渠道"} · {item.content_purpose || "未填目的"}</div></div><span className="text-xs text-gray-400">{item.status}</span></div>
      </Link>
    )}</div>
  </div>;
}
