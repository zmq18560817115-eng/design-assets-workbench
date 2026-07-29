"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ConceptData, DistItem, ProjectOut } from "@/lib/api";

const distributionLabels: Record<string, string> = {
  layout: "排版结构",
  style: "视觉风格",
  alignment: "对齐方式",
  grid: "栅格习惯",
  font: "字体调性",
  text_ratio: "图文比例",
  color_family: "色彩倾向",
};

function Distribution({
  title,
  items,
}: {
  title: string;
  items: DistItem[];
}) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5">
      <h3 className="font-semibold">{title}</h3>
      {items.length === 0 ? (
        <div className="mt-5 text-sm text-gray-400">暂无有效证据</div>
      ) : (
        <div className="mt-5 space-y-4">
          {items.slice(0, 6).map((item) => (
            <div key={item.name}>
              <div className="mb-1.5 flex items-center justify-between gap-4 text-xs">
                <span className="line-clamp-1 text-gray-600">{item.name}</span>
                <span className="shrink-0 font-medium">{item.pct}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-canvas">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max(3, item.pct)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ConceptPage() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [businessLine, setBusinessLine] = useState("");
  const [data, setData] = useState<ConceptData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = (line: string) => {
    setLoading(true);
    setError("");
    api
      .concept(line)
      .then(setData)
      .catch(() => setError("画像读取失败，请确认后端服务已启动。"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    api
      .projects()
      .then((items) => {
        const companyProjects = items.filter((item) => item.business_line);
        setProjects(companyProjects);
        const first = companyProjects[0]?.business_line || "";
        setBusinessLine(first);
        load(first);
      })
      .catch(() => load(""));
  }, []);

  const maturity = useMemo(() => {
    const count = data?.evidence_count || 0;
    if (count >= 30) return { label: "画像稳定", color: "text-emerald-600" };
    if (count >= 10) return { label: "画像形成中", color: "text-amber-600" };
    return { label: "证据不足", color: "text-red-500" };
  }, [data]);

  return (
    <div className="space-y-7">
      <section className="rounded-[30px] bg-ink px-6 py-9 text-white md:px-9">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-white/45">
              Company visual intelligence
            </div>
            <h1 className="mt-3 text-3xl font-semibold">公司视觉画像中心</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/60">
              查看系统从公司成品、模型拆解、人工确认和真实业务采用中学到的视觉倾向。
            </p>
          </div>
          <select
            value={businessLine}
            onChange={(event) => {
              const next = event.target.value;
              setBusinessLine(next);
              load(next);
            }}
            className="min-w-52 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm text-white outline-none"
          >
            <option value="" className="text-ink">
              公司全局画像
            </option>
            {projects.map((project) => (
              <option
                key={project.id}
                value={project.business_line}
                className="text-ink"
              >
                {project.business_line}
              </option>
            ))}
          </select>
        </div>
      </section>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-500">
          {error}
        </div>
      )}

      {loading || !data ? (
        <div className="py-20 text-center text-gray-400">正在聚合公司证据…</div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["公司成品", data.company_published_count],
              ["模型拆解", data.model_analyzed_count],
              ["人工确认", data.trusted_count],
              ["有效证据", data.evidence_count],
              ["加权证据量", data.weighted_total],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-line bg-white p-5">
                <div className="text-xs text-gray-400">{label}</div>
                <div className="mt-2 text-3xl font-semibold">{value}</div>
              </div>
            ))}
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-emerald-200 bg-emerald-50/50 p-6">
              <h2 className="text-lg font-semibold text-emerald-800">
                希望延续的方法
              </h2>
              {data.explicit_guidance.keep.length ? (
                <ul className="mt-4 space-y-2 text-sm text-gray-700">
                  {data.explicit_guidance.keep.map((item) => (
                    <li key={item.text} className="rounded-xl bg-white p-3">
                      {item.text}
                      <span className="ml-2 text-xs text-gray-400">
                        {item.count} 次确认
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-gray-400">
                  等待人工审核填写明确的延续规则。
                </p>
              )}
            </div>
            <div className="rounded-3xl border border-red-200 bg-red-50/50 p-6">
              <h2 className="text-lg font-semibold text-red-700">
                应避免的问题
              </h2>
              {data.explicit_guidance.avoid.length ? (
                <ul className="mt-4 space-y-2 text-sm text-gray-700">
                  {data.explicit_guidance.avoid.map((item) => (
                    <li key={item.text} className="rounded-xl bg-white p-3">
                      {item.text}
                      <span className="ml-2 text-xs text-gray-400">
                        {item.count} 次确认
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-gray-400">
                  等待人工审核填写明确的避坑规则。
                </p>
              )}
            </div>
          </section>

          <section className="rounded-3xl border border-line bg-white p-6 md:p-8">
            <div className="grid gap-7 lg:grid-cols-[1fr_320px]">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-semibold">
                    {data.scope === "company" ? "公司全局" : data.scope}视觉 DNA
                  </h2>
                  <span className={`text-xs font-medium ${maturity.color}`}>
                    {maturity.label}
                  </span>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  {[
                    ["主导版式", data.visual_dna.top_layout],
                    ["主导风格", data.visual_dna.top_style],
                    ["常用栅格", data.visual_dna.top_grid],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-2xl bg-canvas p-4">
                      <div className="text-xs text-gray-400">{label}</div>
                      <div className="mt-2 text-sm font-medium leading-6">
                        {value || "证据不足"}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  {data.visual_dna.colors.slice(0, 8).map((color) => (
                    <div key={color.hex} className="text-center">
                      <div
                        className="h-12 w-12 rounded-xl border border-line"
                        style={{ backgroundColor: color.hex }}
                        title={color.hex}
                      />
                      <div className="mt-1 text-[10px] text-gray-400">
                        {color.hex}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <aside className="rounded-2xl bg-canvas p-5">
                <div className="text-xs font-semibold text-gray-700">证据说明</div>
                <ul className="mt-3 space-y-2 text-xs leading-5 text-gray-500">
                  <li>公司成品证明“历史上真实做过”。</li>
                  <li>模型拆解负责把视觉转成结构化知识。</li>
                  <li>人工确认表示“希望继续保持”。</li>
                  <li>公司推荐与真实业务采用拥有最高权重。</li>
                </ul>
                <div className="mt-5 grid gap-2">
                  <Link
                    href="/training"
                    className="rounded-xl bg-ink px-4 py-2.5 text-center text-sm text-white"
                  >
                    继续人工训练
                  </Link>
                  <Link
                    href="/service"
                    className="rounded-xl border border-line bg-white px-4 py-2.5 text-center text-sm"
                  >
                    使用画像生成方向
                  </Link>
                </div>
              </aside>
            </div>
          </section>

          <section>
            <div className="mb-4">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
                Weighted distributions
              </div>
              <h2 className="mt-2 text-xl font-semibold">加权偏好分布</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(distributionLabels).map(([key, label]) => (
                <Distribution
                  key={key}
                  title={label}
                  items={data.distributions[key] || []}
                />
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-line bg-white p-6 md:p-8">
            <h2 className="text-xl font-semibold">当前可复用原则</h2>
            {data.principles.length === 0 ? (
              <p className="mt-4 text-sm text-gray-400">
                证据不足，完成首批人工确认后再生成稳定原则。
              </p>
            ) : (
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {data.principles.map((principle, index) => (
                  <div
                    key={`${principle}-${index}`}
                    className="rounded-2xl bg-canvas p-4 text-sm leading-7 text-gray-600"
                  >
                    <span className="mr-2 font-semibold text-accent">
                      0{index + 1}
                    </span>
                    {principle}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
