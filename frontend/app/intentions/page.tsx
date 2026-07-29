"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  api,
  BusinessRequirementCreate,
  BusinessRequirementMatch,
} from "@/lib/api";
import { LayoutWireframe } from "@/components/layout-wireframe";
import { Card, Tag } from "@/components/ui";

const initialForm: BusinessRequirementCreate = {
  title: "",
  request_text: "",
  industry: "",
  product_category: "",
  channel: "",
  canvas_ratio: "2:3",
  orientation: "portrait",
  campaign_stage: "",
  business_goal: "",
  target_audience: "",
  key_message: "",
  mandatory_elements: [],
  information_density: "medium",
  reference_case_ids: [],
  created_by: "",
  status: "ready",
};

export default function IntentionsPage() {
  const [form, setForm] = useState(initialForm);
  const [mandatoryText, setMandatoryText] = useState("");
  const [referenceText, setReferenceText] = useState("");
  const [result, setResult] = useState<BusinessRequirementMatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = <K extends keyof BusinessRequirementCreate>(
    key: K,
    value: BusinessRequirementCreate[K]
  ) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const requirement = await api.createBusinessRequirement({
        ...form,
        mandatory_elements: mandatoryText
          .split(/[、,，\n]/)
          .map((item) => item.trim())
          .filter(Boolean),
        reference_case_ids: referenceText
          .split(/[、,，\s]/)
          .map(Number)
          .filter((value) => Number.isInteger(value) && value > 0),
      });
      setResult(await api.matchBusinessRequirement(requirement.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "业务需求匹配失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <section className="rounded-[28px] border border-line bg-white p-6 shadow-[0_18px_60px_rgba(45,45,80,0.06)] md:p-8">
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            Business layout brief
          </div>
          <h1 className="mt-2 text-3xl font-bold">业务排版意向</h1>
          <p className="mt-2 text-sm leading-6 text-gray-500">
            输入真实业务约束，系统只依据人工确认骨架和排版模式进行可解释匹配，不使用公司偏好评分。
          </p>
        </div>

        <form onSubmit={submit} className="mt-7 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-3">
            <input
              required
              value={form.title}
              onChange={(event) => set("title", event.target.value)}
              placeholder="需求名称，例如：吸奶器新品小红书种草长图"
              className="w-full rounded-xl border border-line px-4 py-3 text-sm outline-none focus:border-accent"
            />
            <textarea
              required
              value={form.request_text}
              onChange={(event) => set("request_text", event.target.value)}
              rows={7}
              placeholder="完整业务需求：需要突出什么、信息如何展开、用户看完要理解或行动什么。"
              className="w-full resize-none rounded-xl border border-line px-4 py-3 text-sm leading-6 outline-none focus:border-accent"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <input
                value={form.key_message}
                onChange={(event) => set("key_message", event.target.value)}
                placeholder="核心信息"
                className="rounded-xl border border-line px-4 py-3 text-sm"
              />
              <input
                value={form.target_audience}
                onChange={(event) => set("target_audience", event.target.value)}
                placeholder="目标受众"
                className="rounded-xl border border-line px-4 py-3 text-sm"
              />
              <input
                value={mandatoryText}
                onChange={(event) => setMandatoryText(event.target.value)}
                placeholder="必须出现：产品主图、三项卖点、CTA"
                className="rounded-xl border border-line px-4 py-3 text-sm"
              />
              <input
                value={referenceText}
                onChange={(event) => setReferenceText(event.target.value)}
                placeholder="指定参考案例 ID，可选"
                className="rounded-xl border border-line px-4 py-3 text-sm"
              />
            </div>
          </div>

          <div className="grid content-start gap-3 sm:grid-cols-2">
            {[
              ["industry", "行业／业务线"],
              ["product_category", "产品品类"],
              ["channel", "投放渠道"],
              ["campaign_stage", "业务场景／营销阶段"],
              ["business_goal", "业务目标"],
              ["created_by", "需求创建人 *"],
            ].map(([key, placeholder]) => (
              <input
                key={key}
                required={key === "created_by"}
                value={form[key as keyof BusinessRequirementCreate] as string}
                onChange={(event) =>
                  set(
                    key as keyof BusinessRequirementCreate,
                    event.target.value as never
                  )
                }
                placeholder={placeholder}
                className="rounded-xl border border-line px-4 py-3 text-sm"
              />
            ))}
            <input
              value={form.canvas_ratio}
              onChange={(event) => set("canvas_ratio", event.target.value)}
              placeholder="画布比例，如 2:3"
              className="rounded-xl border border-line px-4 py-3 text-sm"
            />
            <select
              value={form.orientation}
              onChange={(event) =>
                set(
                  "orientation",
                  event.target.value as BusinessRequirementCreate["orientation"]
                )
              }
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm"
            >
              <option value="">不限方向</option>
              <option value="portrait">竖版</option>
              <option value="landscape">横版</option>
              <option value="square">方形</option>
            </select>
            <select
              value={form.information_density}
              onChange={(event) =>
                set(
                  "information_density",
                  event.target.value as BusinessRequirementCreate["information_density"]
                )
              }
              className="rounded-xl border border-line bg-white px-4 py-3 text-sm sm:col-span-2"
            >
              <option value="">不限信息密度</option>
              <option value="low">低密度</option>
              <option value="medium">中密度</option>
              <option value="high">高密度</option>
            </select>
            <button
              disabled={loading}
              className="rounded-xl bg-ink px-5 py-3 text-sm font-medium text-white disabled:opacity-50 sm:col-span-2"
            >
              {loading ? "正在匹配…" : "保存需求并匹配排版知识"}
            </button>
          </div>
        </form>
        {error && <p className="mt-4 text-sm text-rose-500">{error}</p>}
      </section>

      {result && (
        <>
          <section>
            <div className="flex items-end justify-between">
              <div>
                <div className="text-xs text-gray-400">
                  需求 #{result.requirement.id}
                </div>
                <h2 className="mt-1 text-2xl font-semibold">匹配排版模式</h2>
              </div>
              <div className="text-xs text-gray-400">
                共 {result.pattern_matches.length} 个模式
              </div>
            </div>
            <div className="mt-4 grid gap-5 lg:grid-cols-3">
              {result.pattern_matches.map((match) => (
                <Card key={match.pattern.id}>
                  <div className="rounded-xl bg-gray-50 p-4">
                    <LayoutWireframe
                      blueprint={match.pattern}
                      className="max-h-[280px] max-w-[260px]"
                    />
                  </div>
                  <div className="mt-4 flex items-start justify-between gap-2">
                    <h3 className="font-semibold">{match.pattern.name}</h3>
                    <span className="rounded-full bg-lilac px-2 py-1 text-xs text-accent">
                      {match.score.toFixed(0)} 分
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {match.reasons.map((reason) => (
                      <Tag key={reason}>{reason}</Tag>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-semibold">相关案例参考</h2>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {result.case_matches.map((match) => (
                <Link key={match.case_id} href={`/cases/${match.case_id}`}>
                  <Card className="transition hover:border-accent">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{match.name}</div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {match.reasons.map((reason) => (
                            <Tag key={reason}>{reason}</Tag>
                          ))}
                        </div>
                      </div>
                      <span className="text-sm font-semibold text-accent">
                        {match.score.toFixed(0)}
                      </span>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
