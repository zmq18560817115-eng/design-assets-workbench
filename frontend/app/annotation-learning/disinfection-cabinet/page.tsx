"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";

type Region = {
  id: string; type: "layout_block" | "product_image" | "main_text";
  x: number; y: number; width: number; height: number; confidence: number;
};
type Annotation = {
  id: number; filename: string; image_url: string; status: string; reviewer: string;
  regions: Region[]; warnings: string[]; canvas_width: number; canvas_height: number;
  project_key: string; page_role: string; dataset_split: string; annotation_version: number;
};

const colors: Record<Region["type"], string> = {
  layout_block: "#ef4444", product_image: "#1687ff", main_text: "#2fad38",
};

export default function DisinfectionCabinetAnnotationPage() {
  const [items, setItems] = useState<Annotation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reviewer, setReviewer] = useState("设计负责人张茗淇");
  const [notice, setNotice] = useState("");
  const [draftRegions, setDraftRegions] = useState<Region[]>([]);
  const [projectKey, setProjectKey] = useState("");
  const [pageRole, setPageRole] = useState("other");
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [evaluation, setEvaluation] = useState<Record<string, unknown>>({});
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? items[0], [items, selectedId]);

  async function load() {
    const response = await fetch("/api/disinfection-annotations", { cache: "no-store" });
    const data = await response.json();
    setItems(data.items ?? []);
    const [summaryResponse, evaluationResponse, runsResponse] = await Promise.all([
      fetch("/api/disinfection-annotations/report/summary", { cache: "no-store" }),
      fetch("/api/disinfection-annotations/evaluation", { cache: "no-store" }),
      fetch("/api/disinfection-decomposition-runs", { cache: "no-store" }),
    ]);
    setSummary(await summaryResponse.json());
    setEvaluation(await evaluationResponse.json());
    setRuns((await runsResponse.json()).items ?? []);
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!selected) return;
    setDraftRegions(selected.regions.map((region) => ({ ...region })));
    setProjectKey(selected.project_key);
    setPageRole(selected.page_role);
  }, [selected]);

  function updateRegion(index: number, field: keyof Region, value: string) {
    setDraftRegions((current) => current.map((region, regionIndex) => (
      regionIndex === index
        ? { ...region, [field]: field === "type" ? value : Number(value) }
        : region
    )) as Region[]);
  }

  async function save() {
    if (!selected) return;
    const response = await fetch(`/api/disinfection-annotations/${selected.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ regions: draftRegions, project_key: projectKey, page_role: pageRole, reviewer }),
    });
    if (!response.ok) { setNotice(await response.text()); return; }
    setNotice("修改已保存为新版本；如原先已验证，会自动退回待审核。");
    await load();
  }

  async function verify() {
    if (!selected) return;
    const response = await fetch(`/api/disinfection-annotations/${selected.id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer }),
    });
    if (!response.ok) { setNotice(await response.text()); return; }
    setNotice("已人工确认；该条现在可以进入统计证据。");
    await load();
    const pending = items.find((item) => item.id > selected.id && item.status === "pending_review")
      ?? items.find((item) => item.status === "pending_review");
    if (pending) setSelectedId(pending.id);
  }

  const counts = items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1; return acc;
  }, {});

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif", color: "#172033" }}>
      <h1>消毒柜公司成品图标注学习</h1>
      <p>共 {items.length} 张 · 待审核 {counts.pending_review ?? 0} · 已验证 {counts.verified ?? 0}</p>
      <p style={{ color: "#9a6700" }}>AI/解析器只提出候选框；点击人工确认前，不计入学习证据。</p>
      <div style={{ display: "flex", gap: 12, marginBottom: 18 }}>
        <pre style={{ flex: 1, padding: 12, background: "#f6f7f9", overflow: "auto" }}>规律统计：{JSON.stringify(summary, null, 2)}</pre>
        <pre style={{ flex: 1, padding: 12, background: "#f6f7f9", overflow: "auto" }}>Holdout 评估：{JSON.stringify(evaluation, null, 2)}</pre>
      </div>
      <details style={{ marginBottom: 18 }}>
        <summary>AI 初始蓝图、人工最终蓝图与证据追踪（{runs.length} 次）</summary>
        <pre style={{ padding: 12, background: "#f6f7f9", overflow: "auto", maxHeight: 360 }}>{JSON.stringify(runs, null, 2)}</pre>
      </details>
      <div style={{ display: "grid", gridTemplateColumns: "260px minmax(320px, 1fr) minmax(320px, 1fr)", gap: 20 }}>
        <aside style={{ maxHeight: "75vh", overflow: "auto", border: "1px solid #dfe3eb", borderRadius: 10 }}>
          {items.map((item) => (
            <button key={item.id} onClick={() => setSelectedId(item.id)} style={{
              display: "block", width: "100%", padding: 12, textAlign: "left",
              border: 0, borderBottom: "1px solid #eee", background: selected?.id === item.id ? "#eef5ff" : "white",
            }}>
              {item.filename}<br /><small>{item.status} · v{item.annotation_version}</small>
            </button>
          ))}
        </aside>
        {selected ? <>
          <section>
            <h2>标注成品图</h2>
            <Image src={selected.image_url} alt={selected.filename} width={selected.canvas_width} height={selected.canvas_height} unoptimized style={{ width: "100%", height: "auto", maxHeight: "70vh", objectFit: "contain", background: "#f6f7f9" }} />
          </section>
          <section>
            <h2>结构框架</h2>
            <div style={{ position: "relative", width: "100%", aspectRatio: `${selected.canvas_width}/${selected.canvas_height}`, background: "#f8f9fb", border: "1px solid #ccd2dc" }}>
              {draftRegions.map((region) => (
                <div key={region.id} title={`${region.type} ${region.confidence}`} style={{
                  position: "absolute", left: `${region.x * 100}%`, top: `${region.y * 100}%`,
                  width: `${region.width * 100}%`, height: `${region.height * 100}%`,
                  border: `2px solid ${colors[region.type]}`, boxSizing: "border-box",
                }} />
              ))}
            </div>
            <p>红：排版块 · 蓝：产品图 · 绿：主文字</p>
            <p>候选框 {draftRegions.length} 个；警告：{selected.warnings.join("、") || "无"}</p>
            <div style={{ maxHeight: 240, overflow: "auto" }}>
              {draftRegions.map((region, index) => (
                <div key={region.id} style={{ display: "grid", gridTemplateColumns: "120px repeat(4, 72px) 44px", gap: 5, marginBottom: 6 }}>
                  <select value={region.type} onChange={(e) => updateRegion(index, "type", e.target.value)}>
                    <option value="layout_block">排版块</option>
                    <option value="product_image">产品图</option>
                    <option value="main_text">主文字</option>
                  </select>
                  {(["x", "y", "width", "height"] as const).map((field) => (
                    <input key={field} aria-label={`${region.id}-${field}`} type="number" min="0" max="1" step="0.001" value={region[field]} onChange={(e) => updateRegion(index, field, e.target.value)} />
                  ))}
                  <button onClick={() => setDraftRegions((current) => current.filter((_, i) => i !== index))}>删</button>
                </div>
              ))}
            </div>
            <button onClick={() => setDraftRegions((current) => [...current, {
              id: `manual-${Date.now()}`, type: "layout_block", x: 0.1, y: 0.1,
              width: 0.2, height: 0.1, confidence: 1,
            }])}>新增框</button>
            <div style={{ marginTop: 10 }}>
              <label>项目/页面组 <input value={projectKey} onChange={(e) => setProjectKey(e.target.value)} style={{ padding: 8, margin: 8 }} /></label>
              <label>页面角色
                <select value={pageRole} onChange={(e) => setPageRole(e.target.value)} style={{ padding: 8, margin: 8 }}>
                  {["cover_hook", "problem_statement", "cause_explanation", "product_display", "function_explanation", "parameter_comparison", "usage_step", "service_assurance", "conclusion", "call_to_action", "other"].map((role) => <option key={role}>{role}</option>)}
                </select>
              </label>
            </div>
            <label>审核人 <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ padding: 8, margin: 8 }} /></label>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={save} style={{ padding: "10px 18px" }}>保存修订版本</button>
              <button onClick={verify} disabled={selected.status === "verified"} style={{ padding: "10px 18px" }}>验证并打开下一张</button>
            </div>
            {notice && <p>{notice}</p>}
          </section>
        </> : <p>数据库暂无标注，请先执行导入脚本。</p>}
      </div>
    </main>
  );
}
