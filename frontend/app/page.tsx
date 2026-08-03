"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, CaseOut } from "@/lib/api";
import { Card } from "@/components/ui";

export default function Dashboard() {
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [pendingAnnotations, setPendingAnnotations] = useState(0);
  useEffect(() => {
    api.cases().then(setCases).catch(() => setCases([]));
    fetch("/api/layout-annotations/report/summary?product_category=消毒柜", { cache: "no-store" })
      .then((response) => response.json())
      .then((data) => setPendingAnnotations(Number(data.pending_review ?? 0)))
      .catch(() => setPendingAnnotations(0));
  }, []);
  const tasks = useMemo(() => [
    ["待AI分析", cases.filter((item) => !item.analysis).length],
    ["分析失败", cases.filter((item) => item.analysis?.generation_mode === "heuristic_fallback").length],
    ["待补充业务信息", cases.filter((item) => !item.product_name || !item.content_purpose).length],
    ["待人工审核", cases.filter((item) => item.trust_status === "ai_unverified").length + pendingAnnotations],
    ["已确认蓝图", cases.filter((item) => item.trust_status === "verified" || item.trust_status === "company_recommended").length],
    ["待审核排版模式", 0], ["最近业务检索", 0],
  ] as const, [cases, pendingAnnotations]);
  const next = tasks[1][1] ? "/assets?tab=review" : pendingAnnotations ? "/annotation-learning" : tasks[3][1] ? "/assets?tab=review" : tasks[2][1] ? "/assets?tab=library" : "/patterns";
  return <div className="space-y-8">
    <header className="rounded-[28px] bg-ink px-8 py-10 text-white md:px-12">
      <div className="text-xs uppercase tracking-[.22em] text-white/60">Today&apos;s workbench</div>
      <h1 className="mt-3 text-4xl font-semibold">今天需要处理的工作</h1>
      <p className="mt-3 text-sm text-white/70">优先处理失败任务，再审核拆解、补充业务信息和确认候选模式。</p>
      <Link href={next} className="mt-7 inline-flex rounded-xl bg-white px-6 py-3 text-sm font-semibold text-ink">继续处理下一条</Link>
      {pendingAnnotations > 0 && (
        <Link href="/annotation-learning" className="ml-3 mt-7 inline-flex rounded-xl border border-white/30 px-6 py-3 text-sm font-semibold text-white">
          审核消毒柜彩框标注（{pendingAnnotations}）
        </Link>
      )}
    </header>
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {tasks.map(([label,count]) => <Card key={label}><div className="text-3xl font-semibold">{count}</div><div className="mt-2 text-sm text-gray-500">{label}</div></Card>)}
    </section>
  </div>;
}
