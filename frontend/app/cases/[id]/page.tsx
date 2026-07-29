"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, CaseOut } from "@/lib/api";
import { LayoutBlueprintEditor } from "@/components/layout-blueprint-editor";
import { Tag } from "@/components/ui";

export default function CaseDetail() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<CaseOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .case(id)
      .then(setItem)
      .catch(() => setError("素材不存在"));
  }, [id]);

  if (error) return <p className="text-sm text-rose-500">{error}</p>;
  if (!item) return <p className="text-sm text-gray-500">正在读取素材…</p>;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/cases" className="text-sm text-gray-500 hover:text-accent">
          ← 返回素材库
        </Link>
        <Link
          href="/analyze"
          className="rounded-xl border border-line bg-white px-4 py-2 text-sm hover:border-accent"
        >
          继续上传素材
        </Link>
      </div>

      <section className="grid gap-8 rounded-3xl border border-line bg-white p-5 md:p-7 lg:grid-cols-[minmax(320px,0.9fr)_1.1fr]">
        <div className="rounded-2xl bg-canvas p-3">
          {item.image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.image.url}
              alt={item.name}
              className="mx-auto max-h-[680px] w-auto rounded-xl border border-line bg-white object-contain"
            />
          )}
        </div>

        <div className="flex flex-col">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            Source asset
          </div>
          <h1 className="mt-2 text-3xl font-semibold">{item.name}</h1>
          <p className="mt-3 text-sm leading-7 text-gray-500">
            {item.summary || "原始素材已入库，下面仅进行排版框架拆解。"}
          </p>

          <dl className="mt-7 grid gap-3 sm:grid-cols-2">
            {[
              ["产品品类", item.product_category || "未填写"],
              ["内容类型", item.content_type || "未识别"],
              ["素材分类", item.asset_category === "layout" ? "排版" : item.asset_category],
              ["排版子类", item.asset_subcategory || "未分类"],
              ["使用场景", item.scene || "未填写"],
              ["上传人", item.image?.uploader || "未记录"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-line p-3">
                <dt className="text-[11px] text-gray-400">{label}</dt>
                <dd className="mt-1 text-sm">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-5 flex flex-wrap gap-1.5">
            {item.tags.slice(0, 12).map((tag) => (
              <Tag key={tag.id}>{tag.name}</Tag>
            ))}
          </div>

          {item.image?.source_url && (
            <a
              href={item.image.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-auto pt-6 text-sm text-accent hover:underline"
            >
              查看原始来源 →
            </a>
          )}
        </div>
      </section>

      <LayoutBlueprintEditor caseId={item.id} />
    </div>
  );
}
