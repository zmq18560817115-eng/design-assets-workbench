"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, Tag } from "@/components/ui";
import {
  api,
  BusinessRequirement,
  LayoutSearchResponse,
  LayoutSearchResult,
} from "@/lib/api";

const scoreLabels: Record<string, string> = {
  business_scene: "业务场景",
  required_modules: "必需模块",
  layout_structure: "画布结构",
  information_density: "信息密度",
  visual_style: "视觉风格",
  verification: "人工验证",
};

function ResultCard({
  item,
  runId,
  reviewer,
  onMessage,
}: {
  item: LayoutSearchResult;
  runId: number;
  reviewer: string;
  onMessage: (value: string) => void;
}) {
  async function feedback(
    relevance: "relevant" | "partially_relevant" | "irrelevant"
  ) {
    const resultType = item.result_type;
    if (resultType === "external_reference") {
      onMessage("外部参考不进入公司业务验收反馈。");
      return;
    }
    if (!reviewer.trim()) {
      onMessage("请先填写反馈人。");
      return;
    }
    try {
      await api.addLayoutSearchFeedback(runId, {
        result_type: resultType,
        result_id: item.id,
        rank: item.rank,
        relevance,
        reviewer: reviewer.trim(),
      });
      onMessage(`已记录“${item.name}”的相关性反馈。`);
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "反馈保存失败");
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-gray-400">
            #{item.rank} · {item.result_type === "pattern" ? "排版模式" : "真实案例"}
          </div>
          <h3 className="mt-1 font-semibold">{item.name}</h3>
        </div>
        <div className="text-3xl font-bold text-accent">{item.total_score}</div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        {Object.entries(item.score_breakdown).map(([key, value]) => (
          <div key={key} className="rounded-lg bg-canvas p-2">
            <div className="text-gray-400">{scoreLabels[key] || key}</div>
            <div className="mt-1 font-semibold">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {item.match_reasons.map((value) => <Tag key={value}>{value}</Tag>)}
      </div>
      <div className="mt-4 grid gap-3 text-xs md:grid-cols-2">
        <div><span className="text-gray-400">已匹配必需模块：</span>{item.matched_required_modules.join("、") || "无明确要求"}</div>
        <div><span className="text-gray-400">缺失模块：</span>{item.missing_required_modules.join("、") || "无"}</div>
        <div><span className="text-gray-400">可复用：</span>{item.reusable_modules.join("、") || "无"}</div>
        <div><span className="text-gray-400">状态：</span>{item.review_status}</div>
      </div>
      {item.adaptation_needed.length > 0 && (
        <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs">
          适配建议：{item.adaptation_needed.join("；")}
        </div>
      )}
      {item.risks.length > 0 && (
        <div className="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-700">
          风险：{item.risks.join("；")}
        </div>
      )}
      <div className="mt-3 text-xs text-gray-400">
        来源案例 {item.source_case_ids.join("、") || "无"} · 蓝图 {item.source_blueprint_ids.join("、") || "无"}
        {item.related_pattern_ids.length > 0 && ` · 关联模式 ${item.related_pattern_ids.join("、")}`}
      </div>
      {item.acceptance_eligible ? (
        <div className="mt-4 grid grid-cols-3 gap-2">
          <button onClick={() => feedback("relevant")} className="rounded-lg bg-emerald-600 px-2 py-2 text-xs text-white">相关</button>
          <button onClick={() => feedback("partially_relevant")} className="rounded-lg border border-amber-300 px-2 py-2 text-xs">部分相关</button>
          <button onClick={() => feedback("irrelevant")} className="rounded-lg border border-rose-200 px-2 py-2 text-xs text-rose-600">不相关</button>
        </div>
      ) : (
        <div className="mt-4 rounded-lg bg-canvas p-3 text-xs text-gray-500">
          外部参考仅供补充查看，不进入公司评分和真实验收。
        </div>
      )}
    </Card>
  );
}

export default function RequirementLayoutSearchPage() {
  const { id } = useParams<{ id: string }>();
  const [requirement, setRequirement] = useState<BusinessRequirement | null>(null);
  const [result, setResult] = useState<LayoutSearchResponse | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.businessRequirement(id).then(setRequirement).catch((error) => setMessage(error.message));
    api.latestRequirementLayoutSearch(id).then(setResult).catch(() => undefined);
  }, [id]);

  async function search(reanalyzeReference = false) {
    setLoading(true);
    setMessage("");
    try {
      const value = await api.searchRequirementLayouts(id, {
        pattern_limit: 10,
        case_limit: 20,
        include_unverified: false,
        reanalyze_reference: reanalyzeReference,
      });
      setResult(value);
      setMessage(`检索完成：${value.patterns.length} 个模式、${value.cases.length} 个案例。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "检索失败");
    } finally {
      setLoading(false);
    }
  }

  if (!requirement) return <p>{message || "加载中…"}</p>;
  const groups = [
    ["推荐排版模式", result?.patterns || []],
    ["推荐真实案例", result?.cases || []],
    ["外部参考（不参与公司评分）", result?.external_references || []],
    ["被约束排除的结果", result?.excluded_results || []],
  ] as const;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[.2em] text-accent">P3 layout retrieval</div>
          <h1 className="mt-2 text-3xl font-bold">{requirement.title}</h1>
          <p className="mt-2 text-sm text-gray-500">基于已确认模式和真实案例的可解释检索，不使用公司偏好权重。</p>
        </div>
        <div className="flex gap-2">
          {requirement.reference_image_path && (
            <button onClick={() => search(true)} disabled={loading} className="rounded-xl border border-line px-4 py-3 text-sm">重新分析参考图</button>
          )}
          <button onClick={() => search(false)} disabled={loading} className="rounded-xl bg-ink px-5 py-3 text-sm text-white">
            {loading ? "检索中…" : "查找排版参考"}
          </button>
        </div>
      </div>

      <Card className="mt-6">
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <div>产品品类：{requirement.product_category || "未限制"}</div>
          <div>渠道：{requirement.channel || "未限制"}</div>
          <div>内容目的：{requirement.content_purpose || "未限制"}</div>
          <div>画布比例：{requirement.canvas_ratio || "未限制"}</div>
          <div>信息密度：{requirement.information_density || "未限制"}</div>
          <div>必需模块：{requirement.required_modules_json.join("、") || "无"}</div>
          <div>禁止模块：{requirement.forbidden_modules_json.join("、") || "无"}</div>
          <div className="md:col-span-2">
            参考图片：
            {requirement.reference_image_path ? (
              <a className="text-accent" href={requirement.reference_image_path} target="_blank">查看原图</a>
            ) : "无"}
          </div>
        </div>
      </Card>

      <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
        <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="反馈人（标记相关性前必填）" className="rounded-xl border border-line bg-white px-4 py-3 text-sm" />
        {result && <div className="rounded-xl bg-canvas px-4 py-3 text-xs text-gray-500">运行 #{result.search_run_id} · {result.scoring_version} · {result.search_summary.elapsed_ms}ms</div>}
      </div>
      {message && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm">{message}</p>}

      {result && groups.map(([title, items]) => (
        <section key={title} className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">{title}</h2>
            <span className="text-sm text-gray-400">{items.length} 项</span>
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            {items.map((item) => (
              <ResultCard key={`${item.result_type}-${item.id}`} item={item} runId={result.search_run_id} reviewer={reviewer} onMessage={setMessage} />
            ))}
            {items.length === 0 && <p className="text-sm text-gray-400">暂无结果。</p>}
          </div>
        </section>
      ))}

      <div className="mt-8"><Link href={`/requirements/${id}`} className="text-sm text-accent">返回需求详情</Link></div>
    </div>
  );
}
