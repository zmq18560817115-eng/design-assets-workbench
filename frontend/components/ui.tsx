import Link from "next/link";
import { ReactNode } from "react";
import { CaseOut } from "@/lib/api";
import { categoryByValue } from "@/lib/categories";

export function Nav() {
  const items = [
    { href: "/", label: "首页" },
    { href: "/search", label: "找灵感" },
    { href: "/cases", label: "素材库" },
    { href: "/patterns", label: "排版模式" },
    { href: "/analyze", label: "上传入库" },
    { href: "/batch", label: "批量导入" },
    { href: "/training", label: "偏好训练" },
    { href: "/service", label: "业务生成" },
    { href: "/concept", label: "公司画像" },
  ];
  return (
    <nav className="sticky top-0 z-30 border-b border-line bg-white/90 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-4 lg:px-10">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-ink text-sm text-white">
            视
          </span>
          设计灵感资产库
        </Link>
        <div className="flex gap-1 text-sm text-gray-600">
          {items.map((i) => (
            <Link
              key={i.href}
              href={i.href}
              className="rounded-full px-4 py-2 transition hover:bg-lilac hover:text-accent"
            >
              {i.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-line bg-white px-2.5 py-1 text-xs text-gray-600">
      {children}
    </span>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-2xl border border-line bg-white p-5 shadow-[0_10px_30px_rgba(28,28,45,0.04)] ${className}`}>
      {children}
    </div>
  );
}

export function CaseCard({ c }: { c: CaseOut }) {
  const trustLabel: Record<string, string> = {
    ai_unverified: "AI未校验",
    verified: "已校验",
    company_recommended: "公司推荐",
  };
  return (
    <Link href={`/cases/${c.id}`}>
      <div className="group overflow-hidden rounded-2xl border border-line bg-white transition duration-200 hover:-translate-y-1 hover:border-accent/40 hover:shadow-xl">
        {c.image && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={c.image.url} alt={c.name} className="h-56 w-full bg-gray-100 object-cover transition duration-300 group-hover:scale-[1.02]" />
        )}
        <div className="p-4">
          <div className="mb-2 flex gap-1.5 text-[10px]">
            <span className="rounded-full bg-accent/10 px-2 py-1 text-accent">
              {categoryByValue(c.asset_category).label}仓库
            </span>
            {c.asset_subcategory && (
              <span className="rounded-full bg-gray-100 px-2 py-1 text-gray-500">
                {c.asset_subcategory}
              </span>
            )}
          </div>
          <div className="flex items-start justify-between gap-3">
            <div className="font-medium group-hover:text-accent">{c.name}</div>
            <span className="shrink-0 rounded-full bg-gray-100 px-2 py-1 text-[10px] text-gray-500">
              {trustLabel[c.trust_status] || "AI未校验"}
            </span>
          </div>
          <div className="mt-2 line-clamp-2 text-xs leading-5 text-gray-500">{c.summary}</div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {c.tags.slice(0, 4).map((t) => (
              <Tag key={t.id}>{t.name}</Tag>
            ))}
          </div>
        </div>
      </div>
    </Link>
  );
}

export function Swatches({ colors }: { colors: string[] }) {
  return (
    <div className="flex gap-1.5">
      {colors.map((c) => (
        <div
          key={c}
          title={c}
          className="h-8 w-8 rounded-md border border-line"
          style={{ backgroundColor: c }}
        />
      ))}
    </div>
  );
}
