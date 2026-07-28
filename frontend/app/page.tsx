"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, CaseOut } from "@/lib/api";
import { CaseCard } from "@/components/ui";
import { ASSET_CATEGORIES } from "@/lib/categories";

const colors = ["bg-lilac", "bg-cyan", "bg-peach", "bg-[#E9F3E8]"];
const topics = ASSET_CATEGORIES.map((item, index) => ({
  ...item,
  title: item.label,
  color: colors[index],
}));

export default function Home() {
  const [cases, setCases] = useState<CaseOut[]>([]);

  useEffect(() => {
    api.cases().then(setCases).catch(() => setCases([]));
  }, []);

  return (
    <div className="space-y-16">
      <section className="relative overflow-hidden rounded-[32px] border border-line bg-white px-6 py-16 text-center shadow-[0_24px_80px_rgba(45,45,80,0.08)] md:px-16">
        <div className="absolute left-[-5rem] top-[-8rem] h-64 w-64 rounded-full bg-lilac blur-3xl" />
        <div className="absolute bottom-[-8rem] right-[-4rem] h-72 w-72 rounded-full bg-cyan blur-3xl" />
        <div className="relative">
          <div className="mb-5 text-xs font-semibold uppercase tracking-[0.24em] text-accent">
            Design intelligence library
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-semibold leading-tight md:text-6xl">
            今天要做什么视觉方向？
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-gray-500 md:text-base">
            输入模糊想法、选择业务场景，或上传一张参考图。系统从团队素材中找到可复用案例，
            并解释它们为什么适合。
          </p>
          <Link
            href="/search"
            className="mx-auto mt-9 flex max-w-3xl items-center justify-between rounded-2xl border border-line bg-canvas px-5 py-4 text-left text-gray-400 transition hover:border-accent/50 hover:bg-white"
          >
            <span>例如：母婴新品首图，温暖但不要太柔弱……</span>
            <span className="rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-white">
              开始搜索
            </span>
          </Link>
          <div className="mt-5 flex flex-wrap justify-center gap-3 text-sm">
            <Link href="/analyze" className="rounded-full border border-line bg-white px-4 py-2 hover:border-accent">
              上传优秀案例
            </Link>
            <Link href="/batch" className="rounded-full border border-line bg-white px-4 py-2 hover:border-accent">
              批量导入素材
            </Link>
            <Link href="/cases" className="rounded-full border border-line bg-white px-4 py-2 hover:border-accent">
              浏览全部素材
            </Link>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">Categories</div>
            <h2 className="mt-2 text-2xl font-semibold">视觉拆解类别</h2>
          </div>
          <Link href="/search" className="text-sm text-accent">按条件查找 →</Link>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {topics.map((topic, index) => (
            <Link
              key={topic.title}
              href={`/cases?asset_category=${topic.value}`}
              className={`${topic.color} min-h-40 rounded-3xl p-6 transition hover:-translate-y-1`}
            >
              <div className="text-xs text-gray-500">0{index + 1}</div>
              <div className="mt-10 text-xl font-semibold">{topic.title}</div>
              <div className="mt-2 text-sm text-gray-500">{topic.note}</div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">Latest assets</div>
            <h2 className="mt-2 text-2xl font-semibold">最近入库</h2>
          </div>
          <Link href="/cases" className="text-sm text-accent">查看全部 →</Link>
        </div>
        {cases.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-white p-16 text-center">
            <div className="text-lg font-medium">素材库还是空的</div>
            <p className="mt-2 text-sm text-gray-500">先上传一张优秀案例，系统会自动拆解并进入公共库。</p>
            <Link href="/analyze" className="mt-5 inline-flex rounded-xl bg-ink px-5 py-3 text-sm text-white">
              上传第一张素材
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cases.slice(0, 12).map((c) => <CaseCard key={c.id} c={c} />)}
          </div>
        )}
      </section>
    </div>
  );
}
