"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, CaseOut } from "@/lib/api";
import { Card, Swatches, Tag } from "@/components/ui";

export default function CaseDetail() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<CaseOut | null>(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [skeleton, setSkeleton] = useState(false);

  useEffect(() => {
    api
      .case(id)
      .then(setC)
      .catch(() => setErr("案例不存在"));
  }, [id]);

  if (err) return <p className="text-gray-500">{err}</p>;
  if (!c) return <p className="text-gray-500">加载中…</p>;
  const a = c.analysis;

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.1fr_1fr]">
      <div>
        {c.image && (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={skeleton ? `/api/cases/${c.id}/overlay` : c.image.url}
              alt={c.name}
              className="w-full rounded-xl border border-line"
            />
            <button
              onClick={() => setSkeleton((s) => !s)}
              className="absolute right-2 top-2 rounded-md bg-ink/80 px-2.5 py-1 text-xs text-gray-200 backdrop-blur hover:bg-ink"
            >
              {skeleton ? "查看原图" : "版式骨架"}
            </button>
          </div>
        )}
        {skeleton && (
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 border border-[#818cf8]" />页边距/内容框
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 border border-[#34d399]" />纵向模块
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 border border-[#fbbf24]" />栅格列
            </span>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {c.tags.map((t) => (
            <Tag key={t.id}>{t.name}</Tag>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold">{c.name}</h1>
          <p className="mt-1 text-sm text-gray-400">{c.summary}</p>
          <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
            <span>
              产品：{c.product_category || "未分类"} · 类型：{c.content_type || "未识别"} ·
              场景：{c.scene || "未识别"}
            </span>
            {a?.analyzed_by && (
              <span
                className={`rounded-full px-2 py-0.5 ${
                  a.analyzed_by === "启发式规则"
                    ? "bg-panel text-gray-400"
                    : "bg-indigo-500/20 text-indigo-300"
                }`}
              >
                {a.analyzed_by === "启发式规则"
                  ? "启发式规则解析"
                  : `${a.analyzed_by} 深度解析`}
              </span>
            )}
            <span className="rounded-full bg-lilac px-2 py-0.5 text-accent">
              {c.trust_status === "company_recommended"
                ? "公司推荐"
                : c.trust_status === "verified"
                ? "已校验"
                : "AI未校验"}
            </span>
          </div>
          {c.image?.source_url && (
            <a
              href={c.image.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-xs text-accent hover:underline"
            >
              查看原始来源
            </a>
          )}
        </div>

        {a && (
          <>
            {/* 拆解重心：排版优先 */}
            <Card className="border-indigo-500/40">
              <div className="mb-2 flex items-center gap-2">
                <span className="rounded bg-indigo-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  拆解重心
                </span>
                <span className="text-sm font-semibold text-gray-200">排版 · 版式结构</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Tag>{a.layout.layout_type}</Tag>
                <Tag>{a.layout.alignment}</Tag>
              </div>
              {/* 硬版式参数 */}
              <div className="mt-3 grid grid-cols-2 gap-2">
                {[
                  ["栅格", a.layout.grid_columns],
                  ["模块", a.layout.modules],
                  ["页边距", a.layout.margins],
                  ["间距", a.layout.spacing],
                  ["内容占比", a.layout.content_ratio],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-md bg-ink px-2 py-1.5">
                    <div className="text-[10px] text-gray-500">{k}</div>
                    <div className="text-xs text-gray-200">{v}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-xs text-gray-400">信息层级</div>
              <ol className="mt-1 space-y-1 text-sm text-gray-300">
                {a.layout.hierarchy.map((h, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-indigo-400">{i + 1}</span>
                    <span>{h}</span>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-xs text-gray-500">
                留白：{a.layout.whitespace}；{a.layout.focal}
              </p>
            </Card>

            <Card className="border-indigo-500/40">
              <div className="mb-2 text-sm font-semibold text-gray-200">文字 · 标题 · 字体</div>
              <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                <div>
                  <div className="text-xs text-gray-500">标题处理</div>
                  <div>{a.typography.title_treatment}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">字体调性</div>
                  <div>{a.typography.font_tone}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">字号对比</div>
                  <div>{a.typography.size_contrast}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">文字占比</div>
                  <div>{a.typography.text_ratio}</div>
                </div>
                <div className="sm:col-span-2">
                  <div className="text-xs text-gray-500">字体搭配</div>
                  <div>{a.typography.pairing}</div>
                </div>
              </div>
            </Card>

            {/* 次要维度：风格与画面 */}
            <div className="pt-1 text-xs font-medium uppercase tracking-wide text-gray-500">
              次要参考 · 视觉风格与画面
            </div>

            <Card>
              <div className="mb-2 text-sm font-semibold text-gray-300">视觉风格</div>
              <div className="flex flex-wrap gap-1.5">
                {a.style.style_tags.map((s) => (
                  <Tag key={s}>{s}</Tag>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-500">
                情绪：{a.style.mood_keywords.join("、")} · 品牌定位：
                {a.style.brand_position}
              </p>
            </Card>

            <Card>
              <div className="mb-2 text-sm font-semibold text-gray-300">色彩体系</div>
              <Swatches colors={a.color.palette} />
              <p className="mt-2 text-xs text-gray-500">{a.color.description}</p>
            </Card>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Card>
                <div className="text-xs font-semibold text-gray-400">构图</div>
                <div className="mt-1 text-sm">{a.composition.type}</div>
              </Card>
              <Card>
                <div className="text-xs font-semibold text-gray-400">光影</div>
                <div className="mt-1 text-sm">{a.light.type}</div>
              </Card>
              <Card>
                <div className="text-xs font-semibold text-gray-400">材质</div>
                <div className="mt-1 text-sm">{a.material}</div>
              </Card>
            </div>

            {a.insights && (
              <Card className="border-indigo-500/40">
                <div className="mb-3 flex items-center gap-2">
                  <span className="rounded bg-indigo-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    AI 深度解析
                  </span>
                  <span className="text-xs text-gray-500">by {a.analyzed_by}</span>
                </div>
                <div className="space-y-3 text-sm">
                  {a.insights.emotion_narrative && (
                    <p className="text-gray-300">{a.insights.emotion_narrative}</p>
                  )}
                  {a.insights.target_audience && (
                    <div>
                      <div className="text-xs text-gray-500">目标受众</div>
                      <div>{a.insights.target_audience}</div>
                    </div>
                  )}
                  {a.insights.applicable_scenes.length > 0 && (
                    <div>
                      <div className="text-xs text-gray-500">适用场景</div>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {a.insights.applicable_scenes.map((s) => (
                          <Tag key={s}>{s}</Tag>
                        ))}
                      </div>
                    </div>
                  )}
                  {[
                    ["色彩角色", a.insights.color_roles],
                    ["构图原理", a.insights.composition_principles],
                    ["专业点评", a.insights.critique],
                    ["提升建议", a.insights.improvement],
                  ].map(([label, items]) =>
                    (items as string[]).length > 0 ? (
                      <div key={label as string}>
                        <div className="text-xs text-gray-500">{label as string}</div>
                        <ul className="mt-1 list-disc space-y-1 pl-5 text-gray-300">
                          {(items as string[]).map((x, i) => (
                            <li key={i}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null
                  )}
                </div>
              </Card>
            )}

            <Card>
              <div className="mb-2 text-sm font-semibold text-gray-300">设计规则</div>
              <div className="text-xs text-gray-400">为什么优秀</div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-gray-300">
                {a.design_rules.why_good.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
              <div className="mt-3 text-xs text-gray-400">可复用方法</div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-gray-300">
                {a.design_rules.reusable_methods.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </Card>

            <Card>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-300">AI 绘图提示词</span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(a.prompt);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="text-xs text-indigo-400 hover:underline"
                >
                  {copied ? "已复制" : "复制"}
                </button>
              </div>
              <pre className="whitespace-pre-wrap rounded-lg bg-ink p-3 text-xs text-gray-300">
                {a.prompt}
              </pre>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
