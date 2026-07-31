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
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? items[0], [items, selectedId]);

  async function load() {
    const response = await fetch("/api/disinfection-annotations", { cache: "no-store" });
    const data = await response.json();
    setItems(data.items ?? []);
  }
  useEffect(() => { void load(); }, []);

  async function verify() {
    if (!selected) return;
    const response = await fetch(`/api/disinfection-annotations/${selected.id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer }),
    });
    if (!response.ok) { setNotice(await response.text()); return; }
    setNotice("已人工确认；该条现在可以进入统计证据。");
    await load();
  }

  const counts = items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1; return acc;
  }, {});

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif", color: "#172033" }}>
      <h1>消毒柜公司成品图标注学习</h1>
      <p>共 {items.length} 张 · 待审核 {counts.pending_review ?? 0} · 已验证 {counts.verified ?? 0}</p>
      <p style={{ color: "#9a6700" }}>AI/解析器只提出候选框；点击人工确认前，不计入学习证据。</p>
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
              {selected.regions.map((region) => (
                <div key={region.id} title={`${region.type} ${region.confidence}`} style={{
                  position: "absolute", left: `${region.x * 100}%`, top: `${region.y * 100}%`,
                  width: `${region.width * 100}%`, height: `${region.height * 100}%`,
                  border: `2px solid ${colors[region.type]}`, boxSizing: "border-box",
                }} />
              ))}
            </div>
            <p>红：排版块 · 蓝：产品图 · 绿：主文字</p>
            <p>候选框 {selected.regions.length} 个；警告：{selected.warnings.join("、") || "无"}</p>
            <label>审核人 <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ padding: 8, margin: 8 }} /></label>
            <button onClick={verify} disabled={selected.status === "verified"} style={{ padding: "10px 18px" }}>验证并进入下一阶段</button>
            {notice && <p>{notice}</p>}
          </section>
        </> : <p>数据库暂无标注，请先执行导入脚本。</p>}
      </div>
    </main>
  );
}
