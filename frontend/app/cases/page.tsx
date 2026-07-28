"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, CaseOut } from "@/lib/api";
import { CaseCard } from "@/components/ui";

function CasesInner() {
  const params = useSearchParams();
  const initialTag = params.get("tag") || "";
  const [q, setQ] = useState("");
  const [tag, setTag] = useState(initialTag);
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [loading, setLoading] = useState(true);

  const load = (query: string, t: string) => {
    setLoading(true);
    api
      .cases(query, t)
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("", initialTag);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTag]);

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">Asset library</div>
          <h1 className="mt-2 text-2xl font-bold">团队视觉素材库</h1>
        </div>
        <Link href="/search" className="rounded-xl bg-ink px-4 py-2.5 text-sm text-white">
          多模态搜索
        </Link>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(q, tag);
        }}
        className="mb-6 flex gap-2 rounded-2xl border border-line bg-white p-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索案例名称、风格、行业…"
          className="flex-1 rounded-xl border-0 bg-canvas px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent/20"
        />
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
