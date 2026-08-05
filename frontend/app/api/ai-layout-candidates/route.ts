import { readFile, writeFile } from "fs/promises";
import path from "path";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Candidate = Record<string, unknown> & {
  candidate_id: string;
  case_count: number;
  product_position: string;
  title_position: string;
  reading_order: string;
  evidence_annotation_ids: number[];
};

const recommendations: Record<string, { decision: string; target?: string; reason: string; name: string }> = {
  "curated-恒温杯-01": { decision: "keep", name: "中心产品·顶部信息", reason: "案例最多，中心产品与顶部文字关系清晰，是高密度信息页的基础模式。" },
  "curated-恒温杯-02": { decision: "keep", name: "左下产品·右侧信息", reason: "案例充足，左右分栏关系明确，可覆盖产品与说明并列页面。" },
  "curated-恒温杯-03": { decision: "merge", target: "curated-恒温杯-01", name: "中心产品·顶部信息（多产品）", reason: "产品和文字位置、阅读方向与核心01一致，差异主要是产品模块数量。" },
  "curated-恒温杯-04": { decision: "keep", name: "左侧产品·右下信息", reason: "左右分栏且文字重心下移，与顶部信息模式差异明显。" },
  "curated-恒温杯-05": { decision: "merge", target: "curated-恒温杯-02", name: "右下产品·左侧信息", reason: "与核心02互为镜像，建议在人工确认后归入左右分栏模式。" },
  "curated-恒温杯-06": { decision: "keep", name: "顶部产品·底部信息", reason: "自上而下的产品先行阅读顺序明确，覆盖参数与说明承接页。" },
  "curated-恒温杯-07": { decision: "merge", target: "curated-恒温杯-04", name: "左侧小产品·右侧密集信息", reason: "左右关系与核心04相同，模块增多和产品缩小属于密度变体。" },
  "curated-恒温杯-08": { decision: "merge", target: "curated-恒温杯-04", name: "左上产品·右下信息", reason: "与核心04共享左产品右文字结构，仅纵向重心不同。" },
  "curated-恒温杯-09": { decision: "merge", target: "curated-恒温杯-01", name: "中心产品·顶部密集信息", reason: "与核心01位置和阅读方向一致，主要是模块数量变体。" },
  "curated-吸奶器-01": { decision: "keep", name: "左上产品·右侧说明", reason: "案例充足，品类代表清晰，覆盖产品与说明横向展开。" },
  "curated-吸奶器-02": { decision: "human", name: "左上产品·下方说明", reason: "产品在上、文字在下，但产品面积较小；需人工判断是否独立于上下结构。" },
  "curated-吸奶器-03": { decision: "merge", target: "curated-恒温杯-01", name: "左侧产品·顶部信息", reason: "阅读顺序与顶部信息核心一致，建议人工确认跨品类复用边界。" },
  "curated-吸奶器-04": { decision: "merge", target: "curated-恒温杯-02", name: "右下产品·顶部信息", reason: "属于左右分栏核心的镜像与重心变体。" },
  "curated-吸奶器-05": { decision: "merge", target: "curated-恒温杯-01", name: "底部产品·顶部信息", reason: "顶部文字到下方产品的阅读关系已由核心01覆盖。" },
  "curated-吸奶器-06": { decision: "merge", target: "curated-吸奶器-01", name: "右上产品·左下说明", reason: "与吸奶器核心01互为镜像，建议合并为横向产品说明模式。" },
  "curated-羊脂膏-01": { decision: "keep", name: "中心单品·顶部卖点", reason: "唯一羊脂膏候选但有7个案例，单品聚焦特征清晰。" },
};

function candidatesPath() {
  const base = process.cwd().endsWith("frontend") ? path.resolve(process.cwd(), "..") : process.cwd();
  return path.join(base, "backend", "acceptance_data", "layout-pattern-discovery", "layout-pattern-candidates.json");
}

function enrich(candidates: Candidate[]) {
  return candidates.map((candidate) => {
    const recommendation = recommendations[candidate.candidate_id] ?? {
      decision: "human", name: String(candidate.candidate_id), reason: "结构差异尚不足以形成确定建议。",
    };
    const target = candidates.find(item => item.candidate_id === recommendation.target);
    const overlap = target
      ? candidate.evidence_annotation_ids.filter(id => target.evidence_annotation_ids.includes(id)).length
      : 0;
    return {
      ...candidate,
      pattern_name_suggestion: String(candidate.human_name ?? recommendation.name),
      system_recommendation: recommendation.decision,
      merge_target_id: recommendation.target ?? "",
      recommendation_reason: recommendation.reason,
      overlap_with_merge_target: overlap,
      is_core_pending: ["keep", "human"].includes(recommendation.decision)
        && !["kept", "rejected", "merged", "owner_confirmed"].includes(String(candidate.human_review_status ?? "")),
    };
  });
}

export async function GET() {
  try {
    const document = JSON.parse(await readFile(candidatesPath(), "utf8"));
    return NextResponse.json({ ...document, candidates: enrich(document.candidates ?? []), verified_writes: 0 });
  } catch {
    return NextResponse.json({ detail: "候选模式尚未生成" }, { status: 503 });
  }
}

export async function PATCH(request: NextRequest) {
  const body = await request.json();
  const filename = candidatesPath();
  const document = JSON.parse(await readFile(filename, "utf8"));
  const candidate = document.candidates?.find((item: Candidate) => item.candidate_id === body.candidate_id);
  if (!candidate) return NextResponse.json({ detail: "候选模式不存在" }, { status: 404 });
  if (typeof body.name === "string" && body.name.trim()) {
    candidate.pattern_name_suggestion = body.name.trim();
    candidate.human_name = body.name.trim();
  }
  if (body.action === "keep") candidate.human_review_status = "kept";
  else if (body.action === "merge") {
    if (!body.merge_target_id || body.merge_target_id === body.candidate_id) {
      return NextResponse.json({ detail: "合并时必须选择另一个目标模式" }, { status: 422 });
    }
    candidate.human_review_status = "merged";
    candidate.merge_target_id = body.merge_target_id;
  } else if (body.action === "reject") candidate.human_review_status = "rejected";
  else if (body.action === "owner_confirm") {
    if (!String(body.reviewer ?? "").trim()) return NextResponse.json({ detail: "负责人姓名不能为空" }, { status: 422 });
    candidate.human_review_status = "owner_confirmed";
    candidate.design_owner = String(body.reviewer).trim();
  } else if (body.action !== "rename") return NextResponse.json({ detail: "非法操作" }, { status: 422 });
  candidate.formal_layout_pattern_created = false;
  candidate.verified_write_count = 0;
  candidate.review_note = "候选审核仅归档决策，不创建或验证正式 LayoutPattern。";
  await writeFile(filename, JSON.stringify(document, null, 2), "utf8");
  return NextResponse.json(candidate);
}
