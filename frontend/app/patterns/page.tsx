"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LayoutWireframe } from "@/components/layout-wireframe";
import { Card, Tag } from "@/components/ui";
import {
  api,
  LayoutPattern,
  LayoutPatternCandidate,
} from "@/lib/api";

export default function LayoutPatternsPage() {
  const [items, setItems] = useState<LayoutPattern[]>([]);
  const [preview, setPreview] = useState<LayoutPatternCandidate[]>([]);
  const [status, setStatus] = useState("");
  const [orientation, setOrientation] = useState("");
  const [canvasRatio, setCanvasRatio] = useState("");
  const [confidence, setConfidence] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  function load() {
    return api.layoutPatterns({
      review_status: status,
      orientation,
      canvas_ratio: canvasRatio,
      confidence_level: confidence,
    }).then(setItems).catch((error) => setMessage(error.message));
  }

  useEffect(() => {
    api.layoutPatterns({
      review_status: status,
      orientation,
      canvas_ratio: canvasRatio,
      confidence_level: confidence,
    }).then(setItems).catch((error) => setMessage(error.message));
  }, [status, orientation, canvasRatio, confidence]);

  async function discover() {
    setLoading(true);
    setMessage("");
    try {
      const result = await api.rebuildLayoutPatterns(true);
      setPreview(result.candidates);
      setMessage(`dry-run 完成：发现 ${result.candidate_count} 个候选，数据库未修改。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "候选发现失败");
    } finally {
      setLoading(false);
    }
  }

  async function rebuild() {
    setLoading(true);
    try {
      const result = await api.rebuildLayoutPatterns(false);
      setMessage(`正式重建完成：新增 ${result.written}、更新 ${result.updated}、保护跳过 ${result.skipped}。`);
      setPreview([]);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "模式重建失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[.2em] text-accent">Layout patterns</div>
          <h1 className="mt-2 text-3xl font-bold">排版模式库</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500">
            从每个案例最新的已确认蓝图中发现相似结构。自动候选必须由设计负责人审核。
          </p>
        </div>
        <button onClick={discover} disabled={loading} className="rounded-xl bg-ink px-5 py-3 text-sm text-white disabled:opacity-50">
          {loading ? "计算中…" : "发现候选模式"}
        </button>
      </div>

      {message && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}

      {preview.length > 0 && (
        <section className="mt-7 rounded-3xl border border-accent/20 bg-lilac/40 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="font-semibold">dry-run 候选预览</h2><p className="mt-1 text-xs text-gray-500">确认结构和证据后再执行，不会覆盖已确认、已停用或人工模式。</p></div>
            <button onClick={rebuild} disabled={loading} className="rounded-xl bg-accent px-4 py-2 text-sm text-white">确认执行归纳</button>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {preview.map(candidate => (
              <Card key={candidate.pattern_code}>
                <LayoutWireframe blueprint={{canvas_ratio:candidate.canvas_ratio,modules_json:candidate.average_positions_json}} showLabels className="max-h-56 max-w-56" />
                <h3 className="mt-4 font-semibold">{candidate.name}</h3>
                <p className="mt-1 text-xs text-gray-500">{candidate.pattern_code}</p>
                <div className="mt-3 flex flex-wrap gap-2"><Tag>证据 {candidate.evidence_count}</Tag><Tag>{candidate.confidence_level}</Tag><Tag>相似度 {(candidate.mean_similarity*100).toFixed(1)}%</Tag></div>
                <p className="mt-3 text-xs text-gray-500">来源案例：{candidate.evidence_case_ids_json.join("、")}</p>
                {candidate.warnings?.map(value => <p key={value} className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-700">{value}</p>)}
              </Card>
            ))}
          </div>
        </section>
      )}

      <div className="mt-7 flex flex-wrap gap-2">
        <select value={status} onChange={e=>setStatus(e.target.value)} className="rounded-xl border border-line bg-white px-3 py-2 text-sm"><option value="">全部状态</option><option value="draft">自动待审核</option><option value="human_edited">旧待审核</option><option value="verified">已确认</option><option value="disabled">已停用</option></select>
        <select value={orientation} onChange={e=>setOrientation(e.target.value)} className="rounded-xl border border-line bg-white px-3 py-2 text-sm"><option value="">全部方向</option><option value="portrait">竖版</option><option value="landscape">横版</option><option value="square">方形</option></select>
        <select value={canvasRatio} onChange={e=>setCanvasRatio(e.target.value)} className="rounded-xl border border-line bg-white px-3 py-2 text-sm"><option value="">全部比例</option><option value="3:4">3:4</option><option value="1:1">1:1</option><option value="16:9">16:9</option></select>
        <select value={confidence} onChange={e=>setConfidence(e.target.value)} className="rounded-xl border border-line bg-white px-3 py-2 text-sm"><option value="">全部可信度</option><option value="candidate">candidate</option><option value="medium">medium</option><option value="high">high</option></select>
      </div>

      <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {items.map(item => (
          <Link href={`/patterns/${item.id}`} key={item.id}>
            <Card className="h-full">
              <LayoutWireframe blueprint={item} showLabels className="max-h-64 max-w-60" />
              <div className="mt-4 flex justify-between gap-2"><h2 className="font-semibold">{item.name}</h2><Tag>{item.review_status === "human_edited" ? "draft" : item.review_status}</Tag></div>
              <p className="mt-2 line-clamp-2 text-xs leading-5 text-gray-500">{item.description || item.usage_notes}</p>
              <div className="mt-3 flex flex-wrap gap-2"><Tag>{item.canvas_ratio}</Tag><Tag>{item.orientation}</Tag><Tag>证据 {item.evidence_count}</Tag><Tag>{item.confidence_level}</Tag></div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
