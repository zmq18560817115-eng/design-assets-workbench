"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

type Region = {
  id: string;
  type: "layout_block" | "product_image" | "main_text";
  x: number; y: number; width: number; height: number; confidence: number;
};
type Annotation = {
  id: number; filename: string; image_url: string; original_image_url: string; status: string; reviewer: string;
  source_type: string; product_category: string; regions: Region[]; warnings: string[];
  canvas_width: number; canvas_height: number; project_key: string; page_role: string;
  dataset_split: string; annotation_version: number;
};

const boxColors: Record<Region["type"], string> = {
  layout_block: "#ef4444", product_image: "#1687ff", main_text: "#2fad38",
};
const roles = [
  "cover_hook", "problem_statement", "cause_explanation", "product_display",
  "function_explanation", "parameter_comparison", "usage_step", "service_assurance",
  "conclusion", "call_to_action", "other",
];

export default function AnnotationLearningPage() {
  const [items, setItems] = useState<Annotation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [category, setCategory] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [reviewStatus, setReviewStatus] = useState("pending_review");
  const [reviewer, setReviewer] = useState("设计负责人张茗淇");
  const [notice, setNotice] = useState("");
  const [regions, setRegions] = useState<Region[]>([]);
  const [projectKey, setProjectKey] = useState("");
  const [pageRole, setPageRole] = useState("other");
  const [productCategory, setProductCategory] = useState("");
  const [summary, setSummary] = useState<Record<string, unknown>>({});

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (category) params.set("product_category", category);
    if (sourceType) params.set("source_type", sourceType);
    if (reviewStatus) params.set("status", reviewStatus);
    const response = await fetch(`/api/layout-annotations?${params}`, { cache: "no-store" });
    const data = await response.json();
    setItems(data.items ?? []);
    const summaryParams = category ? `?product_category=${encodeURIComponent(category)}` : "";
    const summaryResponse = await fetch(`/api/layout-annotations/report/summary${summaryParams}`, { cache: "no-store" });
    setSummary(await summaryResponse.json());
  }, [category, sourceType, reviewStatus]);
  useEffect(() => { void load(); }, [load]);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? items[0],
    [items, selectedId],
  );
  useEffect(() => {
    if (!selected) return;
    setRegions(selected.regions.map((region) => ({ ...region })));
    setProjectKey(selected.project_key);
    setPageRole(selected.page_role);
    setProductCategory(selected.product_category);
  }, [selected]);

  async function save() {
    if (!selected) return;
    const response = await fetch(`/api/layout-annotations/${selected.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        regions, project_key: projectKey, page_role: pageRole,
        product_category: productCategory, reviewer,
      }),
    });
    setNotice(response.ok ? "修订已保存，需再次人工确认后才进入学习证据。" : await response.text());
    if (response.ok) await load();
  }
  async function verify() {
    if (!selected) return;
    const response = await fetch(`/api/layout-annotations/${selected.id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer }),
    });
    setNotice(response.ok ? "已确认，已从默认待审核队列移除并切换到下一条。" : await response.text());
    if (response.ok) {
      setSelectedId(null);
      await load();
    }
  }
  function updateRegion(index: number, field: keyof Region, value: string) {
    setRegions((current) => current.map((region, currentIndex) => (
      currentIndex === index
        ? { ...region, [field]: field === "type" ? value : Number(value) }
        : region
    )) as Region[]);
  }

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif", color: "#172033" }}>
      <h1>全品类排版拆解与学习</h1>
      <p>公司成品形成内部标准；外部素材只作模仿参考，不会自动成为公司推荐。</p>
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <label>产品分类 <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="如：吸奶器" /></label>
        <label>证据来源
          <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
            <option value="">全部</option><option value="company_published">公司成品</option>
            <option value="external_reference">外部参考</option>
          </select>
        </label>
        <label>审核状态
          <select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
            <option value="pending_review">待审核</option>
            <option value="verified">已确认</option>
            <option value="rejected">已拒绝</option>
            <option value="">全部</option>
          </select>
        </label>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "16px 0" }}>
        {[
          ["总标注", summary.total ?? 0],
          ["已人工确认", summary.verified ?? 0],
          ["待审核", summary.pending_review ?? 0],
          ["正式门槛", summary.readiness_threshold ?? 30],
          ["人工数据集", summary.evaluation_ready ? "已就绪" : "未就绪"],
        ].map(([label, value]) => (
          <div key={String(label)} style={{ minWidth: 120, padding: 12, border: "1px solid #dfe3eb", borderRadius: 8, background: "white" }}>
            <small style={{ color: "#687386" }}>{String(label)}</small>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{String(value)}</div>
          </div>
        ))}
      </div>
      <details style={{ marginBottom: 16 }}>
        <summary>查看完整规律统计</summary>
        <pre style={{ padding: 12, background: "#f6f7f9", overflow: "auto", maxHeight: 320 }}>
          {JSON.stringify(summary, null, 2)}
        </pre>
      </details>
      <div style={{ display: "grid", gridTemplateColumns: "250px minmax(300px, 1fr) minmax(360px, 1fr)", gap: 20 }}>
        <aside style={{ maxHeight: "72vh", overflow: "auto", border: "1px solid #dfe3eb" }}>
          {items.map((item) => (
            <button key={item.id} onClick={() => setSelectedId(item.id)} style={{
              display: "block", width: "100%", padding: 10, textAlign: "left",
              border: 0, borderBottom: "1px solid #eee",
              background: selected?.id === item.id ? "#eef5ff" : "white",
            }}>
              {item.filename}<br /><small>{item.product_category} · {item.status} · v{item.annotation_version}</small>
            </button>
          ))}
        </aside>
        {selected ? <>
          <section>
            <h2>无彩框公司成品原图</h2>
            {selected.original_image_url ? (
              <Image src={selected.original_image_url} alt={`${selected.filename} 对应原图`} width={selected.canvas_width}
                height={selected.canvas_height} unoptimized style={{ width: "100%", height: "auto", maxHeight: "32vh", objectFit: "contain" }} />
            ) : (
              <p style={{ padding: 12, background: "#fff5e8", color: "#8a4b08" }}>尚未人工确认无彩框原图配对，不能执行 verified。</p>
            )}
            <h2>彩框标注图</h2>
            <Image src={selected.image_url} alt={selected.filename} width={selected.canvas_width}
              height={selected.canvas_height} unoptimized style={{ width: "100%", height: "auto", maxHeight: "32vh", objectFit: "contain" }} />
          </section>
          <section>
            <h2>结构蓝图</h2>
            <div style={{ position: "relative", width: "100%", aspectRatio: `${selected.canvas_width}/${selected.canvas_height}`, background: "#f8f9fb" }}>
              {regions.map((region) => <div key={region.id} style={{
                position: "absolute", left: `${region.x * 100}%`, top: `${region.y * 100}%`,
                width: `${region.width * 100}%`, height: `${region.height * 100}%`,
                border: `2px solid ${boxColors[region.type]}`, boxSizing: "border-box",
              }} />)}
            </div>
            <p>红：排版模块　蓝：产品图　绿：主要文字</p>
            <div style={{ maxHeight: 220, overflow: "auto", marginBottom: 10 }}>
              {regions.map((region, index) => (
                <div key={region.id} style={{ display: "grid", gridTemplateColumns: "110px repeat(4, 64px) 40px", gap: 4, marginBottom: 5 }}>
                  <select value={region.type} onChange={(event) => updateRegion(index, "type", event.target.value)}>
                    <option value="layout_block">排版块</option><option value="product_image">产品图</option><option value="main_text">主要文字</option>
                  </select>
                  {(["x", "y", "width", "height"] as const).map((field) => (
                    <input key={field} aria-label={`${region.id}-${field}`} type="number" min="0" max="1" step="0.001"
                      value={region[field]} onChange={(event) => updateRegion(index, field, event.target.value)} />
                  ))}
                  <button onClick={() => setRegions((current) => current.filter((_, itemIndex) => itemIndex !== index))}>删</button>
                </div>
              ))}
              <button onClick={() => setRegions((current) => [...current, {
                id: `manual-${Date.now()}`, type: "layout_block", x: 0.1, y: 0.1,
                width: 0.2, height: 0.1, confidence: 1,
              }])}>新增结构框</button>
            </div>
            <label>产品分类 <input value={productCategory} onChange={(event) => setProductCategory(event.target.value)} /></label><br />
            <label>项目/组 <input value={projectKey} onChange={(event) => setProjectKey(event.target.value)} /></label><br />
            <label>页面角色 <select value={pageRole} onChange={(event) => setPageRole(event.target.value)}>
              {roles.map((role) => <option key={role}>{role}</option>)}
            </select></label><br />
            <label>审核人 <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={save}>保存修订</button>
              <button onClick={verify} disabled={selected.source_type !== "company_published" || !selected.original_image_url || !projectKey.trim()}>
                确认并查看下一条
              </button>
            </div>
            <p>{notice}</p>
          </section>
        </> : <p>当前筛选条件下没有标注数据。</p>}
      </div>
    </main>
  );
}
