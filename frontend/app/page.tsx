"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, CaseOut } from "@/lib/api";
import { CaseCard } from "@/components/ui";

const workflow = [
  {
    number: "01",
    title: "上传素材",
    description: "上传单张或批量导入公司成品图，原始素材完整保留。",
    href: "/analyze",
  },
  {
    number: "02",
    title: "框架拆解",
    description: "根据原图内容区域生成只有模块外框的低保真排版骨架。",
    href: "/cases",
  },
  {
    number: "03",
    title: "沉淀模式",
    description: "人工校正并确认骨架，沉淀为可复用排版模式。",
    href: "/patterns",
  },
];

export default function Home() {
  const [cases, setCases] = useState<CaseOut[]>([]);

  useEffect(() => {
    api.cases("", "", "layout").then(setCases).catch(() => setCases([]));
  }, []);

  return (
    <div className="space-y-16">
      <section className="rounded-[28px] border border-line bg-white px-6 py-14 md:px-12 md:py-20">
        <div className="max-w-4xl">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-accent">
            Business layout knowledge base
          </div>
          <h1 className="mt-5 text-4xl font-semibold leading-tight md:text-6xl">
            从成品素材中，
            <br />
            看懂并复用排版框架
          </h1>
          <p className="mt-6 max-w-2xl text-sm leading-7 text-gray-500 md:text-base">
            系统只做排版知识沉淀：保留原始素材，用框体标记标题、主视觉和信息区域，
            经人工校正和确认后自动发现相似结构，由设计负责人审核并沉淀为可追溯的排版模式。
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/analyze"
              className="rounded-xl bg-ink px-6 py-3 text-sm font-medium text-white transition hover:bg-accent"
            >
              上传单张素材
            </Link>
            <Link
              href="/batch"
              className="rounded-xl border border-line bg-white px-6 py-3 text-sm font-medium transition hover:border-accent"
            >
              批量上传素材
            </Link>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-6">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
            Workflow
          </div>
          <h2 className="mt-2 text-2xl font-semibold">当前业务主线</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {workflow.map((item) => (
            <Link
              key={item.number}
              href={item.href}
              className="min-h-52 rounded-3xl border border-line bg-white p-6 transition hover:-translate-y-1 hover:border-accent"
            >
              <div className="text-xs font-medium text-gray-400">{item.number}</div>
              <h3 className="mt-10 text-xl font-semibold">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-gray-500">
                {item.description}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">
              Layout assets
            </div>
            <h2 className="mt-2 text-2xl font-semibold">最近排版素材</h2>
          </div>
          <Link href="/cases" className="text-sm text-accent">
            查看全部素材 →
          </Link>
        </div>
        {cases.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-white p-14 text-center">
            <div className="font-medium">还没有排版素材</div>
            <p className="mt-2 text-sm text-gray-500">
              上传成品图后，系统会保存原图并生成低保真框架。
            </p>
            <Link
              href="/analyze"
              className="mt-5 inline-flex rounded-xl bg-ink px-5 py-3 text-sm text-white"
            >
              上传第一张素材
            </Link>
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cases.slice(0, 12).map((item) => (
              <CaseCard key={item.id} c={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
