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
  annotation_verified: boolean; company_recommended: boolean | null;
  recommendation_status: "unknown" | "recommended" | "not_recommended" | "pending_lead";
  not_recommended_reason: string; avoid_reasons: string[]; keep_reasons: string[];
};
type QueueRecord = { id: number; quality_group: string; missing_types: string[]; problems: string[] };
type QualityQueues = {
  first_manual_review_batch_ids: number[];
  box_fix_ids: number[];
  records: QueueRecord[];
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
  const [qualityQueues, setQualityQueues] = useState<QualityQueues | null>(null);
  const [queueMode, setQueueMode] = useState<"" | "batch1" | "box_fix">("");
  const [pairingConfirmed, setPairingConfirmed] = useState(false);
  const [boxesConfirmed, setBoxesConfirmed] = useState(false);
  const [pageRoleConfirmed, setPageRoleConfirmed] = useState(false);
  const [readingOrder, setReadingOrder] = useState("");
  const [notRecommendedReason, setNotRecommendedReason] = useState("");
  const [avoidReasons, setAvoidReasons] = useState("");
  const [keepReasons, setKeepReasons] = useState("");
  const [leadConfirmed, setLeadConfirmed] = useState(false);

  useEffect(() => {
    fetch("/api/annotation-quality-queues", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => setQualityQueues(data));
  }, []);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (category) params.set("product_category", category);
    if (sourceType) params.set("source_type", sourceType);
    if (reviewStatus) params.set("status", reviewStatus);
    const response = await fetch(`/api/layout-annotations?${params}`, { cache: "no-store" });
    const data = await response.json();
    const loadedItems: Annotation[] = data.items ?? [];
    const queueIds = queueMode === "batch1"
      ? qualityQueues?.first_manual_review_batch_ids
      : queueMode === "box_fix" ? qualityQueues?.box_fix_ids : null;
    setItems(queueIds ? loadedItems.filter((item) => queueIds.includes(item.id)) : loadedItems);
    const summaryParams = category ? `?product_category=${encodeURIComponent(category)}` : "";
    const summaryResponse = await fetch(`/api/layout-annotations/report/summary${summaryParams}`, { cache: "no-store" });
    setSummary(await summaryResponse.json());
  }, [category, sourceType, reviewStatus, queueMode, qualityQueues]);
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
    setPairingConfirmed(false);
    setBoxesConfirmed(false);
    setPageRoleConfirmed(false);
    setReadingOrder(selected.regions.map((region) => region.id).join(" → "));
    setNotRecommendedReason(selected.not_recommended_reason ?? "");
    setAvoidReasons((selected.avoid_reasons ?? []).join("；"));
    setKeepReasons((selected.keep_reasons ?? []).join("；"));
    setLeadConfirmed(false);
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
    const revisionResponse = await fetch(`/api/layout-annotations/${selected.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        regions, project_key: projectKey, page_role: pageRole,
        product_category: productCategory, reviewer,
      }),
    });
    if (!revisionResponse.ok) {
      setNotice(await revisionResponse.text());
      return;
    }
    const response = await fetch(`/api/layout-annotations/${selected.id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer,
        pairing_confirmed: pairingConfirmed,
        boxes_confirmed: boxesConfirmed,
        page_role_confirmed: pageRoleConfirmed,
        reading_order: readingOrder.split(/→|,|，/).map((item) => item.trim()).filter(Boolean),
      }),
    });
    setNotice(response.ok ? "已确认，已从默认待审核队列移除并切换到下一条。" : await response.text());
    if (response.ok) {
      setSelectedId(null);
      await load();
    }
  }
  async function setRecommendation(decision: "recommended" | "not_recommended" | "pending_lead") {
    if (!selected) return;
    const response = await fetch(`/api/layout-annotations/${selected.id}/recommendation`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision, reviewer, lead_confirmed: leadConfirmed,
        not_recommended_reason: notRecommendedReason,
        avoid_reasons: avoidReasons.split(/；|;|\n/).map((item) => item.trim()).filter(Boolean),
        keep_reasons: keepReasons.split(/；|;|\n/).map((item) => item.trim()).filter(Boolean),
      }),
    });
    if (response.ok) {
      const updated: Annotation = await response.json();
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice("公司参考价值已单独保存，不影响拆解确认状态。");
    } else {
      setNotice(await response.text());
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
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <button onClick={() => setQueueMode(queueMode === "batch1" ? "" : "batch1")} style={{ fontWeight: queueMode === "batch1" ? 700 : 400 }}>
          第一批人工审核30张
        </button>
        <button onClick={() => setQueueMode(queueMode === "box_fix" ? "" : "box_fix")} style={{ fontWeight: queueMode === "box_fix" ? 700 : 400 }}>
          框选异常待修复
        </button>
        {queueMode && <span>当前队列：{queueMode === "batch1" ? "首批30张" : `异常${qualityQueues?.box_fix_ids.length ?? 0}张`}</span>}
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
            {qualityQueues?.records.find((record) => record.id === selected.id)?.problems.length ? (
              <div style={{ padding: 10, marginBottom: 10, background: "#fff5e8", color: "#8a4b08" }}>
                框选异常：{qualityQueues.records.find((record) => record.id === selected.id)?.problems.join("；")}
              </div>
            ) : null}
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
            <label>项目/组 <input value={projectKey} onChange={(event) => setProjectKey(event.target.value)} placeholder="无法追溯时填写：历史项目待补充" /></label><br />
            <label>页面角色 <select value={pageRole} onChange={(event) => setPageRole(event.target.value)}>
              {roles.map((role) => <option key={role}>{role}</option>)}
            </select></label><br />
            <label>审核人 <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
            <div style={{ display: "grid", gap: 8, marginTop: 12, padding: 12, border: "1px solid #86b7fe", borderRadius: 8 }}>
              <strong>拆解结果确认</strong>
              <label><input type="checkbox" checked={pairingConfirmed} onChange={(event) => setPairingConfirmed(event.target.checked)} /> 原图和彩框图对应</label>
              <label><input type="checkbox" checked={boxesConfirmed} onChange={(event) => setBoxesConfirmed(event.target.checked)} /> 红、蓝、绿框正确</label>
              <label><input type="checkbox" checked={pageRoleConfirmed} onChange={(event) => setPageRoleConfirmed(event.target.checked)} /> 页面角色已经人工确认</label>
              <label>阅读顺序 <input value={readingOrder} onChange={(event) => setReadingOrder(event.target.value)} placeholder="例如：region-1 → region-2" style={{ width: "100%" }} /></label>
              <small>这里只确认拆解是否准确，与是否推荐作为公司参考无关。</small>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={save}>保存修订</button>
              <button onClick={verify} disabled={!selected.original_image_url || !projectKey.trim() || !reviewer.trim() || !pairingConfirmed || !boxesConfirmed || !pageRoleConfirmed || !readingOrder.trim() || Boolean(qualityQueues?.box_fix_ids.includes(selected.id))}>
                确认拆解准确
              </button>
            </div>
            <div style={{ display: "grid", gap: 8, marginTop: 12, padding: 12, border: "1px solid #f0c36d", borderRadius: 8 }}>
              <strong>公司参考价值</strong>
              <div>当前状态：{selected.recommendation_status === "unknown" ? "未知" : selected.recommendation_status}</div>
              <label><input type="checkbox" checked={leadConfirmed} onChange={(event) => setLeadConfirmed(event.target.checked)} /> 设计负责人已确认本次推荐判断</label>
              <label>不推荐原因 <textarea value={notRecommendedReason} onChange={(event) => setNotRecommendedReason(event.target.value)} /></label>
              <label>应避免的排版问题 <textarea value={avoidReasons} onChange={(event) => setAvoidReasons(event.target.value)} /></label>
              <label>可保留的局部优点 <textarea value={keepReasons} onChange={(event) => setKeepReasons(event.target.value)} /></label>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button onClick={() => setRecommendation("recommended")} disabled={selected.source_type !== "company_published" || !leadConfirmed}>推荐作为公司参考</button>
                <button onClick={() => setRecommendation("not_recommended")}>不推荐作为公司参考</button>
                <button onClick={() => setRecommendation("pending_lead")}>交负责人判断</button>
              </div>
              <small>推荐状态不会改变拆解确认；只有拆解已确认且负责人明确推荐，才可参与模式沉淀。</small>
            </div>
            <p>{notice}</p>
          </section>
        </> : <p>当前筛选条件下没有标注数据。</p>}
      </div>
    </main>
  );
}
