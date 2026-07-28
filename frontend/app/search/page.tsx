"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, SearchHit } from "@/lib/api";

const sources = [
  ["", "全部来源"],
  ["company_published", "公司已发布作品"],
  ["external_reference", "外部优秀案例"],
  ["unused_internal", "未采用参考方案"],
];

function SearchWorkspace() {
  const params = useSearchParams();
  const initialQuery = params.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [product, setProduct] = useState("");
  const [scene, setScene] = useState("");
  const [contentType, setContentType] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [reference, setReference] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    try {
      const value = JSON.parse(localStorage.getItem("selected-case-ids") || "[]");
      if (Array.isArray(value)) setSelected(value.filter((x) => Number.isInteger(x)));
    } catch {
      setSelected([]);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("selected-case-ids", JSON.stringify(selected));
  }, [selected]);

  useEffect(() => {
    if (initialQuery) void runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  const selectedCases = useMemo(
    () => results.filter((item) => selected.includes(item.case.id)),
    [results, selected]
  );

  const onReference = (file: File | null) => {
    setReference(file);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(file ? URL.createObjectURL(file) : "");
  };

  const runSearch = async (event?: FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await api.search({
        query_text: query,
        product,
        scene,
        content_type: contentType,
        source_type: sourceType,
        reference_image: reference,
      });
      setResults(data);
      setSearched(true);
    } catch {
      setError("搜索失败，请确认后端服务和AI拆解服务已启动。");
    } finally {
      setLoading(false);
    }
  };

  const toggle = (id: number) => {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  };

  return (
    <div className="pb-28">
      <section className="rounded-[28px] border border-line bg-white p-6 shadow-[0_18px_60px_rgba(45,45,80,0.06)] md:p-8">
        <div className="mb-6">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Multimodal search</div>
          <h1 className="mt-2 text-3xl font-semibold">搜索可复用的视觉案例</h1>
          <p className="mt-2 text-sm text-gray-500">文字、业务条件和参考图可以单独使用，也可以组合检索。</p>
        </div>

        <form onSubmit={runSearch} className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="描述你的需求，例如：母婴新品首图，温暖、专业、信息不要太满"
              className="min-h-14 flex-1 rounded-2xl border border-line bg-canvas px-5 outline-none transition focus:border-accent focus:bg-white"
            />
            <label className="flex min-h-14 cursor-pointer items-center gap-3 rounded-2xl border border-dashed border-line bg-white px-5 text-sm text-gray-500 hover:border-accent">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="参考图" className="h-10 w-10 rounded-lg object-cover" />
              ) : (
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-lilac text-accent">＋</span>
              )}
              <span>{reference ? reference.name : "上传参考图"}</span>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => onReference(event.target.files?.[0] || null)}
              />
            </label>
            <button
              disabled={loading}
              className="min-h-14 rounded-2xl bg-ink px-8 font-medium text-white transition hover:bg-accent disabled:opacity-50"
            >
              {loading ? "正在理解…" : "搜索案例"}
            </button>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <input
              value={product}
              onChange={(event) => setProduct(event.target.value)}
              placeholder="产品，如：吸奶器"
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <input
              value={scene}
              onChange={(event) => setScene(event.target.value)}
              placeholder="场景，如：新品上市"
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <input
              value={contentType}
              onChange={(event) => setContentType(event.target.value)}
              placeholder="内容类型，如：海报"
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <select
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            >
              {sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </form>
        {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
      </section>

      <section className="mt-9">
        <div className="mb-5 flex items-end justify-between">
          <div>
            <h2 className="text-xl font-semibold">
              {searched ? `找到 ${results.length} 个相关案例` : "等待搜索"}
            </h2>
            <p className="mt-1 text-xs text-gray-400">选择多个案例后，可在底部托盘统一确认。</p>
          </div>
          {results.length > 0 && (
            <button
              onClick={() => setSelected(results.map((item) => item.case.id))}
              className="text-sm text-accent"
            >
              全选本页
            </button>
          )}
        </div>

        {searched && results.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-white p-16 text-center text-gray-500">
            没有找到符合条件的素材，可以减少筛选条件或先上传优秀案例。
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {results.map((item) => {
              const active = selected.includes(item.case.id);
              return (
                <article
                  key={item.case.id}
                  className={`group relative overflow-hidden rounded-2xl border bg-white transition ${
                    active ? "border-accent ring-2 ring-accent/20" : "border-line hover:-translate-y-1 hover:shadow-xl"
                  }`}
                >
                  <button
                    onClick={() => toggle(item.case.id)}
                    className={`absolute right-3 top-3 z-10 grid h-8 w-8 place-items-center rounded-full border text-sm shadow-sm ${
                      active ? "border-accent bg-accent text-white" : "border-white bg-white/90 text-gray-500"
                    }`}
                    aria-label={active ? "取消选择" : "选择案例"}
                  >
                    {active ? "✓" : "＋"}
                  </button>
                  <Link href={`/cases/${item.case.id}`}>
                    {item.case.image && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={item.case.image.url}
                        alt={item.case.name}
                        className="h-64 w-full bg-gray-100 object-cover transition duration-300 group-hover:scale-[1.02]"
                      />
                    )}
                    <div className="p-4">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="line-clamp-1 font-medium">{item.case.name}</h3>
                        <span className="text-xs font-semibold text-accent">{Math.round(item.score)}%</span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-gray-500">{item.case.summary}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {item.reasons.slice(0, 2).map((reason) => (
                          <span key={reason} className="rounded-full bg-canvas px-2.5 py-1 text-[10px] text-gray-500">
                            {reason}
                          </span>
                        ))}
                      </div>
                    </div>
                  </Link>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {selected.length > 0 && (
        <div className="fixed bottom-5 left-1/2 z-40 flex w-[min(920px,calc(100%-2rem))] -translate-x-1/2 items-center justify-between gap-4 rounded-2xl bg-ink px-5 py-4 text-white shadow-2xl">
          <div>
            <div className="font-medium">已选择 {selected.length} 个案例</div>
            <div className="text-xs text-gray-400">
              {selectedCases.length > 0 ? selectedCases.map((item) => item.case.name).slice(0, 2).join("、") : "选择已保存在当前浏览器"}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setSelected([])} className="rounded-xl px-4 py-2 text-sm text-gray-300 hover:bg-white/10">
              清空
            </button>
            <button className="rounded-xl bg-white px-5 py-2 text-sm font-medium text-ink">
              确认案例选择
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<p className="text-gray-500">加载搜索工作台…</p>}>
      <SearchWorkspace />
    </Suspense>
  );
}
