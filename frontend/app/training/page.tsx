"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  CaseOut,
  ProjectOut,
  TrainingOverview,
  TrainingReadiness,
} from "@/lib/api";

const categoryLabels: Record<string, string> = {
  layout: "排版",
  style: "风格",
  color: "色彩",
  photo: "实拍图",
};

const trustLabels: Record<string, string> = {
  ai_unverified: "待审核",
  verified: "已确认",
  company_recommended: "公司推荐",
  rejected: "不采用",
};

const gateLabels: Record<string, string> = {
  company_assets: "成品",
  model_analyzed: "模型",
  human_verified: "确认",
  company_recommended: "推荐",
  service_runs: "生成",
  adopted_runs: "采用",
};

export default function TrainingPage() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<number>();
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [overview, setOverview] = useState<TrainingOverview | null>(null);
  const [readiness, setReadiness] = useState<TrainingReadiness[]>([]);
  const [category, setCategory] = useState("");
  const [trustStatus, setTrustStatus] = useState("ai_unverified");
  const [analysisMode, setAnalysisMode] = useState("model");
  const [selected, setSelected] = useState<number[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [businessLine, setBusinessLine] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadOverview = () =>
    api.trainingOverview().then(setOverview).catch(() => setOverview(null));
  const loadReadiness = () =>
    api.trainingReadiness().then(setReadiness).catch(() => setReadiness([]));

  const loadCases = (
    nextProjectId = projectId,
    nextCategory = category,
    nextTrust = trustStatus,
    nextAnalysisMode = analysisMode
  ) => {
    setLoading(true);
    return api
      .cases(
        "",
        "",
        nextCategory,
        "",
        nextProjectId,
        nextTrust,
        nextAnalysisMode
      )
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    Promise.all([
      api.projects(),
      api.trainingOverview(),
      api.trainingReadiness(),
    ])
      .then(([projectList, metrics, roadmap]) => {
        setProjects(projectList);
        setOverview(metrics);
        setReadiness(roadmap);
        const preferred =
          projectList.find(
            (project) =>
              project.business_line && project.model_analyzed_count > 0
          ) ||
          projectList.find((project) => project.is_gold) ||
          projectList[0];
        const nextId = preferred?.id;
        setProjectId(nextId);
        return api.cases("", "", "", "", nextId, "ai_unverified", "model");
      })
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  }, []);

  const allSelected =
    cases.length > 0 && cases.every((item) => selected.includes(item.id));

  const applyBatch = async (
    action: "confirm" | "recommend" | "reject"
  ) => {
    if (!reviewer.trim()) {
      setMessage("请先填写审核人。");
      return;
    }
    if (selected.length === 0) {
      setMessage("请至少选择一个案例。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const result = await api.batchReview(
        selected,
        action,
        reviewer,
        notes,
        businessLine
      );
      setMessage(`已处理 ${result.updated_count} 个案例。`);
      setSelected([]);
      await Promise.all([loadCases(), loadOverview(), loadReadiness()]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量处理失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-7">
      <section className="rounded-[28px] bg-ink px-6 py-8 text-white md:px-9">
        <div className="grid gap-8 lg:grid-cols-[1fr_340px] lg:items-end">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-white/50">
              Preference training
            </div>
            <h1 className="mt-3 text-3xl font-semibold">公司偏好训练工作台</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/65">
              审核黄金候选、记录采用与淘汰依据，并把真实业务选择沉淀为可计算的公司视觉画像。
            </p>
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between text-xs text-white/60">
              <span>画像成熟度</span>
              <span>{overview?.maturity_score ?? 0}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/15">
              <div
                className="h-full rounded-full bg-[#A8FFCF] transition-all"
                style={{ width: `${overview?.maturity_score ?? 0}%` }}
              />
            </div>
            <div className="mt-3 text-xs text-white/50">
              目标：30 个可信案例、12 个公司推荐、50 条偏好事件
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
        {[
          ["素材总量", overview?.total_cases ?? 0],
          ["待审核", overview?.unreviewed_cases ?? 0],
          ["已确认", overview?.verified_cases ?? 0],
          ["公司推荐", overview?.recommended_cases ?? 0],
          ["偏好事件", overview?.preference_events ?? 0],
          ["业务产出", overview?.service_runs ?? 0],
          ["最终采用", overview?.adopted_service_runs ?? 0],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-line bg-white p-5">
            <div className="text-xs text-gray-400">{label}</div>
            <div className="mt-2 text-3xl font-semibold">{value}</div>
          </div>
        ))}
      </section>

      <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
              Training roadmap
            </div>
            <h2 className="mt-2 text-xl font-semibold">五大品类训练路线图</h2>
            <p className="mt-2 text-xs leading-5 text-gray-400">
              每条业务线依次通过素材、模型、人工、推荐、真实生成和采用反馈六个门槛。
            </p>
          </div>
          <Link href="/concept" className="text-sm text-accent">
            查看公司画像 →
          </Link>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {readiness.map((item) => (
            <div key={item.business_line} className="rounded-2xl border border-line p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-semibold">{item.business_line}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    下一步：{item.next_action}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-semibold">{item.score}%</div>
                  <div className="text-[10px] text-gray-400">训练就绪度</div>
                </div>
              </div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-canvas">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${item.score}%` }}
                />
              </div>
              <div className="mt-4 grid grid-cols-6 gap-2">
                {Object.entries(item.gates).map(([key, gate]) => (
                  <div
                    key={key}
                    className={`rounded-xl px-2 py-2 text-center ${
                      gate.met
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-canvas text-gray-400"
                    }`}
                  >
                    <div className="text-[10px]">{gateLabels[key] || key}</div>
                    <div className="mt-1 text-xs font-semibold">
                      {gate.current}/{gate.target}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
        <div className="mb-5">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
            Business lines
          </div>
          <h2 className="mt-2 text-xl font-semibold">业务线画像覆盖</h2>
          <p className="mt-2 text-xs leading-5 text-gray-400">
            只有填写了业务线并经过人工确认的案例，才会影响该业务线的生成服务。
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-4">
          {Object.entries(overview?.business_line_coverage || {}).map(
            ([line, item]) => (
              <div key={line} className="rounded-2xl border border-line p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{line}</span>
                  <span
                    className={`rounded-full px-2 py-1 text-[10px] ${
                      item.trusted >= 10
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-amber-50 text-amber-600"
                    }`}
                  >
                    {item.trusted >= 10 ? "形成中" : "证据不足"}
                  </span>
                </div>
                <div className="mt-3 text-xs text-gray-500">
                  成品 {item.company_published} · 模型拆解{" "}
                  {item.model_analyzed} · 人工确认 {item.trusted} · 推荐{" "}
                  {item.recommended}
                </div>
              </div>
            )
          )}
        </div>
      </section>

      <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
              Coverage
            </div>
            <h2 className="mt-2 text-xl font-semibold">分类训练覆盖</h2>
          </div>
          <Link href="/cases" className="text-sm text-accent">
            查看完整素材库 →
          </Link>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          {Object.entries(categoryLabels).map(([key, label]) => {
            const item = overview?.category_coverage[key] || {
              total: 0,
              trusted: 0,
              recommended: 0,
            };
            return (
              <button
                key={key}
                onClick={() => {
                  const next = category === key ? "" : key;
                  setCategory(next);
                  setSelected([]);
                  loadCases(projectId, next, trustStatus, analysisMode);
                }}
                className={`rounded-2xl border p-4 text-left transition ${
                  category === key
                    ? "border-accent bg-accent/5"
                    : "border-line hover:border-accent/40"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{label}</span>
                  <span className="text-xs text-gray-400">{item.total} 条</span>
                </div>
                <div className="mt-3 text-xs text-gray-500">
                  可信 {item.trusted} · 推荐 {item.recommended}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1fr_300px]">
        <div className="rounded-3xl border border-line bg-white p-5 md:p-7">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">黄金候选审核队列</h2>
              <p className="mt-1 text-xs text-gray-400">
                当前显示 {cases.length} 条，已选择 {selected.length} 条
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={projectId || ""}
                onChange={(event) => {
                  const next = Number(event.target.value) || undefined;
                  setProjectId(next);
                  setSelected([]);
                  loadCases(next, category, trustStatus);
                }}
                className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.is_gold ? "黄金候选 · " : ""}
                    {project.name}（模型 {project.model_analyzed_count}/成品{" "}
                    {project.company_published_count}）
                  </option>
                ))}
              </select>
              <select
                value={trustStatus}
                onChange={(event) => {
                  const next = event.target.value;
                  setTrustStatus(next);
                  setSelected([]);
                  loadCases(projectId, category, next);
                }}
                className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm"
              >
                <option value="ai_unverified">待审核</option>
                <option value="verified">已确认</option>
                <option value="company_recommended">公司推荐</option>
                <option value="rejected">不采用</option>
                <option value="">全部状态</option>
              </select>
              <select
                value={analysisMode}
                onChange={(event) => {
                  const next = event.target.value;
                  setAnalysisMode(next);
                  setSelected([]);
                  loadCases(projectId, category, trustStatus, next);
                }}
                className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm"
              >
                <option value="model">仅模型深度拆解</option>
                <option value="local">仅本地结构拆解</option>
                <option value="">全部拆解来源</option>
              </select>
            </div>
          </div>

          <label className="mb-4 flex items-center gap-2 text-sm text-gray-500">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={() =>
                setSelected(allSelected ? [] : cases.map((item) => item.id))
              }
            />
            选择当前页全部案例
          </label>

          {loading ? (
            <div className="py-16 text-center text-gray-400">正在加载候选…</div>
          ) : cases.length === 0 ? (
            <div className="py-16 text-center text-gray-400">
              当前条件下没有待处理案例。
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {cases.map((item) => {
                const active = selected.includes(item.id);
                return (
                  <div
                    key={item.id}
                    className={`overflow-hidden rounded-2xl border transition ${
                      active ? "border-accent ring-2 ring-accent/10" : "border-line"
                    }`}
                  >
                    <button
                      className="relative block w-full text-left"
                      onClick={() =>
                        setSelected((current) =>
                          active
                            ? current.filter((id) => id !== item.id)
                            : [...current, item.id]
                        )
                      }
                    >
                      {item.image && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={item.image.url}
                          alt={item.name}
                          className="h-44 w-full bg-gray-100 object-cover"
                        />
                      )}
                      <span
                        className={`absolute left-3 top-3 grid h-6 w-6 place-items-center rounded-full border text-xs ${
                          active
                            ? "border-accent bg-accent text-white"
                            : "border-white bg-white/90 text-transparent"
                        }`}
                      >
                        ✓
                      </span>
                    </button>
                    <div className="p-3">
                      <div className="flex items-center justify-between gap-2 text-[11px] text-gray-400">
                        <span>{categoryLabels[item.asset_category] || item.asset_category}</span>
                        <span>{trustLabels[item.trust_status] || item.trust_status}</span>
                      </div>
                      <Link
                        href={`/cases/${item.id}`}
                        className="mt-2 line-clamp-1 block text-sm font-medium hover:text-accent"
                      >
                        {item.name}
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <aside className="h-fit rounded-3xl border border-line bg-white p-5 xl:sticky xl:top-24">
          <h3 className="font-semibold">批量沉淀选择</h3>
          <p className="mt-1 text-xs leading-5 text-gray-400">
            只批量处理结论明确的案例；需要改标签或提示词时进入详情页单独校正。
          </p>
          <div className="mt-4 rounded-2xl bg-canvas p-4">
            <div className="text-xs font-semibold text-gray-700">统一判断准则</div>
            <ol className="mt-2 space-y-1.5 text-[11px] leading-5 text-gray-500">
              <li>1. 信息层级是否符合当前品类业务表达？</li>
              <li>2. 是否代表公司希望继续保持的视觉倾向？</li>
              <li>3. 排版方法能否复用到下一次设计？</li>
              <li>4. 是否存在过时、低效或不希望延续的问题？</li>
              <li>5. 模型拆解与原图是否一致，需要校正什么？</li>
            </ol>
          </div>
          <label className="mt-5 block text-xs text-gray-500">
            审核人 *
            <input
              value={reviewer}
              onChange={(event) => setReviewer(event.target.value)}
              placeholder="姓名或岗位"
              className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            />
          </label>
          <label className="mt-3 block text-xs text-gray-500">
            业务线
            <input
              value={businessLine}
              onChange={(event) => setBusinessLine(event.target.value)}
              placeholder="例如：母婴、小家电"
              className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            />
          </label>
          <label className="mt-3 block text-xs text-gray-500">
            判断依据
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="说明采用或淘汰原因"
              rows={3}
              className="mt-1 w-full resize-none rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            />
          </label>
          <div className="mt-4 rounded-xl bg-canvas p-3 text-xs text-gray-500">
            已选择 {selected.length} 个案例
          </div>
          <div className="mt-3 grid gap-2">
            <button
              disabled={saving}
              onClick={() => applyBatch("confirm")}
              className="rounded-xl bg-ink px-4 py-2.5 text-sm text-white disabled:opacity-50"
            >
              批量确认可用
            </button>
            <button
              disabled={saving}
              onClick={() => applyBatch("recommend")}
              className="rounded-xl bg-accent px-4 py-2.5 text-sm text-white disabled:opacity-50"
            >
              标记为公司推荐
            </button>
            <button
              disabled={saving}
              onClick={() => applyBatch("reject")}
              className="rounded-xl border border-red-200 px-4 py-2.5 text-sm text-red-500 disabled:opacity-50"
            >
              批量不采用
            </button>
          </div>
          {message && (
            <div className="mt-3 rounded-xl bg-canvas px-3 py-2 text-xs text-gray-600">
              {message}
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}
