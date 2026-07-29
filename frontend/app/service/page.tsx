"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api, RecommendResult } from "@/lib/api";

const maturityLabels = {
  insufficient: "证据不足",
  growing: "偏好形成中",
  strong: "公司画像稳定",
};

export default function ServicePage() {
  const [text, setText] = useState("");
  const [industry, setIndustry] = useState("");
  const [channel, setChannel] = useState("");
  const [campaignStage, setCampaignStage] = useState("");
  const [businessGoal, setBusinessGoal] = useState("");
  const [reference, setReference] = useState<File | null>(null);
  const [result, setResult] = useState<RecommendResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [actor, setActor] = useState("");
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [outcome, setOutcome] = useState("");
  const [feedbackSaving, setFeedbackSaving] = useState(false);

  const sendFeedback = async (
    next: "adopted" | "rejected" | "needs_revision"
  ) => {
    if (!result || !actor.trim()) {
      setError("记录业务结果前，请填写反馈人。");
      return;
    }
    setFeedbackSaving(true);
    setError("");
    try {
      await api.serviceFeedback(result.run_id, next, actor, feedbackNotes);
      setOutcome(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "结果反馈失败");
    } finally {
      setFeedbackSaving(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() && !reference) {
      setError("请填写业务需求或上传一张意向图。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setResult(
        await api.recommend({
          text,
          industry,
          channel,
          campaign_stage: campaignStage,
          business_goal: businessGoal,
          file: reference,
        })
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "方向生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-7">
      <section className="rounded-[30px] border border-line bg-white p-6 shadow-[0_18px_60px_rgba(45,45,80,0.06)] md:p-9">
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            Company design service
          </div>
          <h1 className="mt-3 text-3xl font-semibold">生成符合公司倾向的视觉方向</h1>
          <p className="mt-3 text-sm leading-7 text-gray-500">
            系统会结合业务需求、意向图、已确认案例和真实采用记录生成方向。公司证据不足时会明确提示，不会伪装成成熟规范。
          </p>
        </div>

        <form onSubmit={submit} className="mt-7 grid gap-4 lg:grid-cols-[1fr_320px]">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="例如：母婴新品首发主视觉，突出专业、安全和温暖，信息层级清楚，后续需要适配小红书与电商详情页。"
            rows={14}
            className="resize-none rounded-2xl border border-line bg-canvas px-5 py-4 text-sm leading-6 outline-none focus:border-accent focus:bg-white"
          />
          <div className="grid gap-3">
            <input
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              placeholder="业务线／行业"
              className="rounded-xl border border-line px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <select
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            >
              <option value="">选择渠道</option>
              <option value="小红书">小红书</option>
              <option value="电商详情页">电商详情页</option>
              <option value="电商首图">电商首图</option>
              <option value="品牌官网">品牌官网</option>
              <option value="线下物料">线下物料</option>
            </select>
            <select
              value={campaignStage}
              onChange={(event) => setCampaignStage(event.target.value)}
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-accent"
            >
              <option value="">选择营销阶段</option>
              <option value="新品预热">新品预热</option>
              <option value="新品首发">新品首发</option>
              <option value="日常种草">日常种草</option>
              <option value="大促转化">大促转化</option>
              <option value="口碑沉淀">口碑沉淀</option>
            </select>
            <input
              value={businessGoal}
              onChange={(event) => setBusinessGoal(event.target.value)}
              placeholder="业务目标，例如：建立专业信任"
              className="rounded-xl border border-line px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <label className="cursor-pointer rounded-xl border border-dashed border-line px-4 py-3 text-sm text-gray-500 hover:border-accent">
              {reference ? reference.name : "上传意向图（可选）"}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => setReference(event.target.files?.[0] || null)}
              />
            </label>
            <button
              disabled={loading}
              className="rounded-xl bg-ink px-5 py-3 text-sm font-medium text-white hover:bg-accent disabled:opacity-50"
            >
              {loading ? "正在生成…" : "生成业务视觉方向"}
            </button>
          </div>
        </form>
        {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
      </section>

      {result && (
        <>
          <section className="rounded-3xl border border-line bg-white p-5 md:p-6">
            <div className="grid gap-5 lg:grid-cols-[1fr_380px] lg:items-end">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
                  Business outcome · #{result.run_id}
                </div>
                <h2 className="mt-2 text-xl font-semibold">这次产出最终是否被业务采用？</h2>
                <p className="mt-2 text-sm leading-6 text-gray-500">
                  这个结果会反哺本次引用的公司证据案例，是系统形成真实业务倾向最重要的数据。
                </p>
              </div>
              <div className="grid gap-2">
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={actor}
                    onChange={(event) => setActor(event.target.value)}
                    placeholder="反馈人 *"
                    className="rounded-xl border border-line px-3 py-2.5 text-sm outline-none focus:border-accent"
                  />
                  <input
                    value={feedbackNotes}
                    onChange={(event) => setFeedbackNotes(event.target.value)}
                    placeholder="采用／放弃原因"
                    className="rounded-xl border border-line px-3 py-2.5 text-sm outline-none focus:border-accent"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    ["adopted", "已采用"],
                    ["needs_revision", "需调整"],
                    ["rejected", "不采用"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      disabled={feedbackSaving}
                      onClick={() =>
                        sendFeedback(
                          value as "adopted" | "rejected" | "needs_revision"
                        )
                      }
                      className={`rounded-xl px-3 py-2.5 text-sm ${
                        outcome === value
                          ? "bg-accent text-white"
                          : "border border-line hover:border-accent"
                      }`}
                    >
                      {outcome === value ? `✓ ${label}` : label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section
            className={`rounded-2xl border p-5 ${
              result.preference_applied
                ? "border-emerald-200 bg-emerald-50"
                : "border-amber-200 bg-amber-50"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">
                  {result.preference_applied
                    ? "已应用公司偏好证据"
                    : "当前仅提供通用方向"}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  画像范围：{result.company_evidence.scope} ·{" "}
                  {maturityLabels[result.company_maturity]} · 公司证据{" "}
                  {result.company_evidence.evidence_cases} 条（成品{" "}
                  {result.company_evidence.company_published_cases}／人工确认{" "}
                  {result.company_evidence.trusted_cases}／模型拆解{" "}
                  {result.company_evidence.model_analyzed_cases}）
                </div>
              </div>
              <Link href="/training" className="text-sm text-accent">
                继续训练公司画像 →
              </Link>
            </div>
          </section>

          <section className="grid gap-5 lg:grid-cols-[1fr_360px]">
            <div className="rounded-3xl border border-line bg-white p-6">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
                Visual directions
              </div>
              <h2 className="mt-2 text-xl font-semibold">推荐视觉方向</h2>
              <div className="mt-5 grid gap-3">
                {result.directions.map((direction, index) => (
                  <div
                    key={`${direction}-${index}`}
                    className="rounded-2xl bg-canvas p-4 text-sm leading-7 text-gray-700"
                  >
                    <span className="mr-3 font-semibold text-accent">
                      0{index + 1}
                    </span>
                    {direction}
                  </div>
                ))}
              </div>
            </div>

            <aside className="rounded-3xl border border-line bg-white p-6">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
                Company evidence
              </div>
              <h2 className="mt-2 text-xl font-semibold">公司依据</h2>
              <dl className="mt-5 space-y-4 text-sm">
                {[
                  ["常用版式", result.company_evidence.layouts],
                  ["倾向风格", result.company_evidence.styles],
                  ["常用栅格", result.company_evidence.grids],
                  ["色彩倾向", result.company_evidence.color_families],
                ].map(([label, values]) => (
                  <div key={label as string}>
                    <dt className="text-xs text-gray-400">{label}</dt>
                    <dd className="mt-1 leading-6">
                      {(values as string[]).join("、") || "证据不足"}
                    </dd>
                  </div>
                ))}
              </dl>
              {result.evidence_case_ids.length > 0 && (
                <div className="mt-5 flex flex-wrap gap-2">
                  {result.evidence_case_ids.map((id) => (
                    <Link
                      key={id}
                      href={`/cases/${id}`}
                      className="rounded-full bg-lilac px-3 py-1.5 text-xs text-accent"
                    >
                      证据案例 #{id}
                    </Link>
                  ))}
                </div>
              )}
            </aside>
          </section>

          <section className="rounded-3xl bg-ink p-6 text-white md:p-8">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-white/40">
                  Whiteboard prompt
                </div>
                <h2 className="mt-2 text-xl font-semibold">白板生图提示词</h2>
              </div>
              <button
                onClick={async () => {
                  await navigator.clipboard.writeText(result.prompt);
                  setCopied(true);
                }}
                className="rounded-xl bg-white px-4 py-2 text-sm text-ink"
              >
                {copied ? "已复制" : "复制提示词"}
              </button>
            </div>
            <p className="mt-5 whitespace-pre-wrap text-sm leading-8 text-white/75">
              {result.prompt}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
