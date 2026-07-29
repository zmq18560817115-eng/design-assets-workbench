"use client";

import Link from "next/link";
import { useState } from "react";
import { api, CaseOut } from "@/lib/api";
import { Card } from "@/components/ui";
import { LayoutBlueprintEditor } from "@/components/layout-blueprint-editor";
import { categoryByValue } from "@/lib/categories";

export default function AnalyzePage() {
  const [preview, setPreview] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CaseOut | null>(null);
  const [error, setError] = useState("");
  const [sourceType, setSourceType] = useState("external_reference");
  const [sourceUrl, setSourceUrl] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [rightsNote, setRightsNote] = useState("");
  const [assetSubcategory, setAssetSubcategory] = useState("");

  const onPick = (nextFile: File | null) => {
    setResult(null);
    setError("");
    setFile(nextFile);
    setPreview(nextFile ? URL.createObjectURL(nextFile) : "");
  };

  const run = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      setResult(
        await api.analyze(file, {
          source_type: sourceType,
          source_url: sourceUrl,
          product_category: productCategory,
          rights_note: rightsNote,
          asset_category: "layout",
          asset_subcategory: assetSubcategory,
        })
      );
    } catch {
      setError("上传或排版拆解失败，请确认后端服务已启动。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          Upload layout asset
        </div>
        <h1 className="mt-2 text-3xl font-semibold">上传排版素材</h1>
        <p className="mt-2 text-sm leading-6 text-gray-500">
          保存原始成品图，并根据图片内容区域生成只有外框的低保真排版骨架。
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <Card>
          <label className="flex min-h-[420px] cursor-pointer items-center justify-center rounded-2xl border-2 border-dashed border-line bg-canvas p-4 hover:border-accent">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="待上传素材"
                className="max-h-[520px] max-w-full rounded-xl border border-line bg-white object-contain"
              />
            ) : (
              <div className="text-center">
                <div className="font-medium">选择一张成品图</div>
                <div className="mt-2 text-sm text-gray-400">PNG / JPG / WEBP</div>
              </div>
            )}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => onPick(event.target.files?.[0] || null)}
            />
          </label>
        </Card>

        <Card className="h-fit">
          <div className="text-sm font-semibold">素材信息</div>
          <div className="mt-4 grid gap-3">
            <select
              value={assetSubcategory}
              onChange={(event) => setAssetSubcategory(event.target.value)}
              className="rounded-xl border border-line bg-white px-3 py-3 text-sm"
            >
              <option value="">选择排版子类</option>
              {categoryByValue("layout").subcategories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <input
              value={productCategory}
              onChange={(event) => setProductCategory(event.target.value)}
              placeholder="产品品类，例如：吸奶器"
              className="rounded-xl border border-line px-3 py-3 text-sm"
            />
            <select
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
              className="rounded-xl border border-line bg-white px-3 py-3 text-sm"
            >
              <option value="company_published">公司已发布成品</option>
              <option value="external_reference">外部参考素材</option>
              <option value="unused_internal">内部未采用方案</option>
            </select>
            <input
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="原始来源链接（可选）"
              className="rounded-xl border border-line px-3 py-3 text-sm"
            />
            <input
              value={rightsNote}
              onChange={(event) => setRightsNote(event.target.value)}
              placeholder="素材使用说明（可选）"
              className="rounded-xl border border-line px-3 py-3 text-sm"
            />
          </div>
          <button
            onClick={run}
            disabled={!file || loading}
            className="mt-4 w-full rounded-xl bg-ink py-3 text-sm font-medium text-white hover:bg-accent disabled:opacity-40"
          >
            {loading ? "正在上传并拆解框架…" : "上传并生成排版框架"}
          </button>
          {error && <p className="mt-3 text-sm text-rose-500">{error}</p>}
        </Card>
      </div>

      {result && (
        <>
          <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
            <div>
              <div className="font-medium text-emerald-800">素材已入库</div>
              <p className="mt-1 text-sm text-emerald-700">
                {result.name} · 已生成首版低保真排版骨架
              </p>
            </div>
            <Link
              href={`/cases/${result.id}`}
              className="rounded-xl bg-white px-4 py-2 text-sm text-emerald-700"
            >
              打开素材详情 →
            </Link>
          </section>
          <LayoutBlueprintEditor caseId={result.id} />
        </>
      )}
    </div>
  );
}
