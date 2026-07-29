"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  CaseOut,
  ProjectOut,
  TrainingOverview,
  TrainingReadiness,
  ReviewQuality,
  CategorySuggestion,
  CategorySuggestionJob,
  CategoryDiscovery,
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
  category_balance: "四类",
  model_analyzed: "模型",
  human_verified: "确认",
  company_recommended: "推荐",
  service_runs: "生成",
  adopted_runs: "采用",
};

const serviceModeLabels = {
  reference_only: "仅供参考",
  pilot: "业务试运行",
  operational: "可正式使用",
};

export default function TrainingPage() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<number>();
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [overview, setOverview] = useState<TrainingOverview | null>(null);
  const [readiness, setReadiness] = useState<TrainingReadiness[]>([]);
  const [quality, setQuality] = useState<Record<number, ReviewQuality>>({});
  const [suggestions, setSuggestions] = useState<
    Record<number, CategorySuggestion>
  >({});
  const [categoryJob, setCategoryJob] =
    useState<CategorySuggestionJob | null>(null);
  const [discovery, setDiscovery] = useState<CategoryDiscovery[]>([]);
  const [category, setCategory] = useState("");
  const [trustStatus, setTrustStatus] = useState("ai_unverified");
  const [analysisMode, setAnalysisMode] = useState("model");
  const [selected, setSelected] = useState<number[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [businessLine, setBusinessLine] = useState("");
  const [notes, setNotes] = useState("");
  const [keepReasons, setKeepReasons] = useState("");
  const [avoidReasons, setAvoidReasons] = useState("");
  const [targetCategory, setTargetCategory] = useState<
    "layout" | "style" | "color" | "photo"
  >("layout");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadOverview = () =>
    api.trainingOverview().then(setOverview).catch(() => setOverview(null));
  const loadReadiness = () =>
    api.trainingReadiness().then(setReadiness).catch(() => setReadiness([]));
  const loadDiscovery = () =>
    api.categoryDiscovery().then(setDiscovery).catch(() => setDiscovery([]));

  const loadCases = (
    nextProjectId = projectId,
    nextCategory = category,
    nextTrust = trustStatus,
    nextAnalysisMode = analysisMode
  ) => {
    setLoading(true);
    return Promise.all([
      api.cases(
        "",
        "",
        nextCategory,
        "",
        nextProjectId,
        nextTrust,
        nextAnalysisMode
      ),
      api.trainingReviewQuality(nextProjectId),
      api.categorySuggestions(nextProjectId),
    ])
      .then(([caseItems, qualityItems, suggestionItems]) => {
        setCases(caseItems);
        setQuality(
          Object.fromEntries(qualityItems.map((item) => [item.case_id, item]))
        );
        setSuggestions(
          Object.fromEntries(suggestionItems.map((item) => [item.case_id, item]))
        );
      })
      .catch(() => {
        setCases([]);
        setQuality({});
        setSuggestions({});
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    Promise.all([
      api.projects(),
      api.trainingOverview(),
      api.trainingReadiness(),
      api.categoryDiscovery(),
      api.latestCategorySuggestionJob(),
    ])
      .then(
        ([projectList, metrics, roadmap, discoveryItems, latestCategoryJob]) => {
        setProjects(projectList);
        setOverview(metrics);
        setReadiness(roadmap);
        setDiscovery(discoveryItems);
        setCategoryJob(latestCategoryJob);
        const preferred =
          projectList.find(
            (project) =>
              project.business_line && project.model_analyzed_count > 0
          ) ||
          projectList.find((project) => project.is_gold) ||
          projectList[0];
        const nextId = preferred?.id;
        setProjectId(nextId);
        return Promise.all([
          api.cases("", "", "", "", nextId, "ai_unverified", "model"),
          api.trainingReviewQuality(nextId),
          api.categorySuggestions(nextId),
        ]);
        }
      )
      .then(([caseItems, qualityItems, suggestionItems]) => {
        setCases(caseItems);
        setQuality(
          Object.fromEntries(qualityItems.map((item) => [item.case_id, item]))
        );
        setSuggestions(
          Object.fromEntries(suggestionItems.map((item) => [item.case_id, item]))
        );
      })
      .catch(() => {
        setCases([]);
        setQuality({});
        setSuggestions({});
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (
      !categoryJob ||
      (categoryJob.status !== "queued" && categoryJob.status !== "running")
    ) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const next = await api.categorySuggestionJob(categoryJob.id);
        setCategoryJob(next);
        if (next.status !== "queued" && next.status !== "running") {
          const [suggestionItems, discoveryItems] = await Promise.all([
            api.categorySuggestions(projectId),
            api.categoryDiscovery(),
          ]);
          setSuggestions(
            Object.fromEntries(
              suggestionItems.map((item) => [item.case_id, item])
            )
          );
          setDiscovery(discoveryItems);
          setSaving(false);
          setMessage(
            `分类任务完成：成功 ${next.succeeded} 条，失败 ${next.failed} 条。请人工确认后再归类。`
          );
        }
      } catch {
        // Keep the last visible progress and try again on the next interval.
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [categoryJob?.id, categoryJob?.status, projectId]);

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
        businessLine,
        keepReasons.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        avoidReasons.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
      );
      setMessage(`已处理 ${result.updated_count} 个案例。`);
      setSelected([]);
      await Promise.all([
        loadCases(),
        loadOverview(),
        loadReadiness(),
        loadDiscovery(),
      ]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量处理失败");
    } finally {
      setSaving(false);
    }
  };

  const applyCategory = async () => {
    if (!reviewer.trim()) {
      setMessage("请先填写归类操作人。");
      return;
    }
    if (selected.length === 0) {
      setMessage("请至少选择一个案例。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const result = await api.batchCategorize(
        selected,
        targetCategory,
        reviewer
      );
      setMessage(`已将 ${result.updated_count} 个案例归入${categoryLabels[targetCategory]}。`);
      setSelected([]);
      await Promise.all([
        loadCases(),
        loadOverview(),
        loadReadiness(),
        loadDiscovery(),
      ]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量归类失败");
    } finally {
      setSaving(false);
    }
  };

  const generateCategorySuggestions = async () => {
    if (selected.length === 0) {
      setMessage("请先选择需要模型判断类别的案例。");
      return;
    }
    if (selected.length > 20) {
      setMessage("每次最多生成 20 个分类建议。");
      return;
    }
    setSaving(true);
    setMessage("分类任务已提交，模型将在后台处理…");
    try {
      const job = await api.startCategorySuggestionJob(selected);
      setCategoryJob(job);
      setMessage(`后台分类任务 #${job.id} 已启动，可以继续浏览页面。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "分类建议生成失败");
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
                  <div className="mt-1 text-[10px] text-gray-400">
                    建议负责人：{item.owner_role}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-semibold">{item.score}%</div>
                  <div className="text-[10px] text-gray-400">训练就绪度</div>
                  <div className="mt-1 text-[10px] font-medium text-accent">
                    {serviceModeLabels[item.service_mode]}
                  </div>
                </div>
              </div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-canvas">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${item.score}%` }}
                />
              </div>
              <div className="mt-4 grid grid-cols-7 gap-2">
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
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(item.asset_category_coverage).map(
                  ([categoryKey, coverage]) => (
                    <span
                      key={categoryKey}
                      className={`rounded-full px-2 py-1 text-[10px] ${
                        coverage.met
                          ? "bg-emerald-50 text-emerald-600"
                          : "bg-amber-50 text-amber-600"
                      }`}
                    >
                      {categoryLabels[categoryKey] || categoryKey}{" "}
                      {coverage.current}/{coverage.target}
                    </span>
                  )
                )}
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-[10px] font-semibold text-gray-500">
                    本周执行动作
                  </div>
                  <ul className="mt-2 space-y-1 text-xs text-gray-600">
                    {item.weekly_actions.map((action) => (
                      <li key={action}>· {action}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-[10px] font-semibold text-gray-500">
                    建议优先审核案例
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.review_candidate_ids.length ? (
                      item.review_candidate_ids.map((id) => (
                        <Link
                          key={id}
                          href={`/cases/${id}`}
                          className="rounded-lg bg-white px-2 py-1 text-xs text-accent"
                        >
                          #{id}
                        </Link>
                      ))
                    ) : (
                      <span className="text-xs text-gray-400">
                        当前阶段暂无待审样本
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
        <div className="mb-5">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
            Category discovery
          </div>
          <h2 className="mt-2 text-xl font-semibold">类别补齐候选</h2>
          <p className="mt-2 text-xs leading-5 text-gray-400">
            模型只负责发现可能适合补齐缺口的素材；点击案例查看原图，最终仍由人工确认归类。
          </p>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {discovery.map((line) => {
            const gapCandidates = line.gaps.flatMap((gap) =>
              line.candidates[gap.category]
                .slice(0, gap.needed || 2)
                .map((candidate) => ({ ...candidate, label: gap.label }))
            );
            return (
              <div
                key={line.business_line}
                className="rounded-2xl border border-line p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="font-semibold">{line.business_line}</div>
                    <div className="mt-1 text-xs text-gray-400">
                      已获得模型建议 {line.suggested_count}/{line.total_assets}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    {line.gaps.map((gap) => (
                      <span
                        key={gap.category}
                        className="rounded-full bg-amber-50 px-2 py-1 text-[10px] text-amber-600"
                      >
                        {gap.label}缺 {gap.needed}
                      </span>
                    ))}
                  </div>
                </div>
                {gapCandidates.length ? (
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {gapCandidates.map((candidate) => (
                      <Link
                        key={`${candidate.case_id}-${candidate.suggested_category}`}
                        href={`/cases/${candidate.case_id}`}
                        className="rounded-xl bg-canvas p-3 text-xs hover:ring-1 hover:ring-accent"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            #{candidate.case_id} · {candidate.label}
                          </span>
                          <span className="text-accent">
                            {candidate.confidence}%
                          </span>
                        </div>
                        <div className="mt-1 line-clamp-2 leading-5 text-gray-500">
                          {candidate.reason}
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 rounded-xl bg-canvas p-3 text-xs text-gray-400">
                    后台分类仍在处理，或暂未发现可补齐当前缺口的候选。
                  </div>
                )}
              </div>
            );
          })}
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
                const check = quality[item.id];
                const suggestion = suggestions[item.id];
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
                      {check && (
                        <span
                          className={`absolute right-3 top-3 rounded-full px-2.5 py-1 text-[10px] font-medium ${
                            check.ready
                              ? "bg-emerald-500 text-white"
                              : "bg-amber-400 text-white"
                          }`}
                        >
                          拆解质量 {check.score}
                        </span>
                      )}
                      {suggestion && (
                        <div className="mt-2 rounded-lg bg-blue-50 p-2 text-[10px] leading-4 text-blue-700">
                          模型建议：{categoryLabels[suggestion.suggested_category]}
                          {" · "}
                          {suggestion.confidence}%
                          <div className="mt-1 text-blue-600">
                            {suggestion.reason}
                          </div>
                        </div>
                      )}
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
                      {check && (
                        <div
                          className={`mt-2 text-[10px] leading-4 ${
                            check.ready ? "text-emerald-600" : "text-amber-600"
                          }`}
                        >
                          {check.ready
                            ? "技术检查通过，可进行业务判断"
                            : check.warnings.slice(0, 2).join("；")}
                        </div>
                      )}
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
          <label className="mt-3 block text-xs text-gray-500">
            希望延续的方法
            <textarea
              value={keepReasons}
              onChange={(event) => setKeepReasons(event.target.value)}
              placeholder="每行一项，例如：保留大标题与产品主体的强对比"
              rows={3}
              className="mt-1 w-full resize-none rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            />
          </label>
          <label className="mt-3 block text-xs text-gray-500">
            应避免的问题
            <textarea
              value={avoidReasons}
              onChange={(event) => setAvoidReasons(event.target.value)}
              placeholder="每行一项，例如：避免卖点堆叠导致层级不清"
              rows={3}
              className="mt-1 w-full resize-none rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            />
          </label>
          <div className="mt-4 rounded-xl bg-canvas p-3 text-xs text-gray-500">
            已选择 {selected.length} 个案例
          </div>
          <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
            <select
              value={targetCategory}
              onChange={(event) =>
                setTargetCategory(
                  event.target.value as
                    | "layout"
                    | "style"
                    | "color"
                    | "photo"
                )
              }
              className="rounded-xl border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent"
            >
              <option value="layout">排版素材</option>
              <option value="style">风格素材</option>
              <option value="color">色彩素材</option>
              <option value="photo">实拍图素材</option>
            </select>
            <button
              disabled={saving}
              onClick={applyCategory}
              className="rounded-xl border border-line px-3 py-2.5 text-sm disabled:opacity-50"
            >
              批量归类
            </button>
          </div>
          <button
            disabled={saving}
            onClick={generateCategorySuggestions}
            className="mt-2 w-full rounded-xl border border-blue-200 bg-blue-50 px-3 py-2.5 text-sm text-blue-700 disabled:opacity-50"
          >
            为选中素材生成模型分类建议
          </button>
          {categoryJob &&
            (categoryJob.status === "queued" ||
              categoryJob.status === "running") && (
              <div className="mt-2 rounded-xl bg-blue-50 p-3 text-xs text-blue-700">
                <div className="flex items-center justify-between">
                  <span>后台分类任务 #{categoryJob.id}</span>
                  <span>
                    {categoryJob.completed}/{categoryJob.total}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-blue-100">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all"
                    style={{
                      width: `${
                        categoryJob.total
                          ? (categoryJob.completed / categoryJob.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
                <div className="mt-2 text-[10px] text-blue-500">
                  可以继续浏览页面，任务完成后建议会自动刷新。
                </div>
              </div>
            )}
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
