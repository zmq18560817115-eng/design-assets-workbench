"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, CaseOut } from "@/lib/api";
import { CaseCard } from "@/components/ui";

function CasesInner() {
  const params = useSearchParams();
  const initialTag = params.get("tag") || "";
  const initialCategory = "layout";
  const [q, setQ] = useState("");
  const [tag, setTag] = useState(initialTag);
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [productName, setProductName] = useState("");
  const [contentPurpose, setContentPurpose] = useState("");
  const [pageRole, setPageRole] = useState("");
  const assetCategory = "layout";
  const assetSubcategory = "";

  const load = (
    query: string,
    t: string,
    category = assetCategory,
    subcategory = assetSubcategory
  ) => {
    setLoading(true);
    api
      .cases(query, t, category, subcategory, undefined, "", "", productName, contentPurpose, pageRole)
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("", initialTag, initialCategory, "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTag]);

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">Layout assets</div>
          <h1 className="mt-2 text-2xl font-bold">排版素材库</h1>
          <p className="mt-2 text-sm text-gray-500">保留原始成品图，用于排版框架拆解、校正和模式沉淀。</p>
        </div>
        <Link href="/analyze" className="rounded-xl bg-ink px-4 py-2.5 text-sm text-white">
          上传排版素材
        </Link>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(q, tag);
        }}
        className="mb-6 grid gap-2 rounded-2xl border border-line bg-white p-2 md:grid-cols-4"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索素材名称、产品品类或使用场景…"
          className="flex-1 rounded-xl border-0 bg-canvas px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent/20"
        />
        <input
          value={productName}
          onChange={(e) => setProductName(e.target.value)}
          placeholder="产品名称"
          className="rounded-xl border-0 bg-canvas px-4 py-2.5 outline-none"
        />
        <input
          value={contentPurpose}
          onChange={(e) => setContentPurpose(e.target.value)}
          placeholder="内容用途"
          className="rounded-xl border-0 bg-canvas px-4 py-2.5 outline-none"
        />
        <select
          value={pageRole}
          onChange={(e) => setPageRole(e.target.value)}
          className="rounded-xl border-0 bg-canvas px-4 py-2.5 outline-none"
        >
          <option value="">全部页面角色</option>
          {["cover_hook","problem_statement","cause_explanation","product_display","function_explanation","parameter_comparison","usage_step","service_assurance","conclusion","call_to_action","other"].map((role) => (
            <option key={role} value={role}>{role}</option>
          ))}
        </select>
        <button className="rounded-xl bg-accent px-5 font-medium text-white hover:bg-ink">
          搜索
        </button>
      </form>

      {tag && (
        <div className="mb-4 text-sm text-gray-400">
          标签筛选：<span className="text-indigo-400">{tag}</span>{" "}
          <button
            onClick={() => {
              setTag("");
              load(q, "");
            }}
            className="ml-2 text-gray-500 underline"
          >
            清除
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">加载中…</p>
      ) : cases.length === 0 ? (
        <p className="text-gray-500">没有匹配的案例。</p>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {cases.map((c) => (
            <CaseCard key={c.id} c={c} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CasesPage() {
  return (
    <Suspense fallback={<p className="text-gray-500">加载中…</p>}>
      <CasesInner />
    </Suspense>
  );
}
