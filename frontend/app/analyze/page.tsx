"use client";
import { useState } from "react";
import Link from "next/link";
import { api, CaseOut } from "@/lib/api";
import { Card, Swatches, Tag } from "@/components/ui";
import { ASSET_CATEGORIES, categoryByValue } from "@/lib/categories";

export default function AnalyzePage() {
  const [preview, setPreview] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CaseOut | null>(null);
  const [error, setError] = useState("");
  const [sourceType, setSourceType] = useState("external_reference");
  const [sourceUrl, setSourceUrl] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [rightsNote, setRightsNote] = useState("");
  const [assetCategory, setAssetCategory] = useState("layout");
  const [assetSubcategory, setAssetSubcategory] = useState("");

  const onPick = (f: File | null) => {
    setResult(null);
    setError("");
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : "");
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
          asset_category: assetCategory,
          asset_subcategory: assetSubcategory,
        })
      );
    } catch (e) {
      setError("分析失败，请确认后端服务已启动。");
    } finally {
      setLoading(false);
    }
  };

  const a = result?.analysis;

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">上传优秀案例并AI拆解</h1>
      <p className="mb-6 text-sm text-gray-400">
        上传后自动完成结构化拆解并进入团队公共素材库，默认标记为“AI未校验”。
      </p>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <label className="flex h-64 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-line hover:border-indigo-500">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="预览" className="max-h-60 rounded-md" />
            ) : (
              <span className="text-gray-500">点击选择图片 · PNG / JPG</span>
            )}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => onPick(e.target.files?.[0] || null)}
            />
          </label>
          <button
            onClick={run}
            disabled={!file || loading}
            className="mt-4 w-full rounded-lg bg-indigo-500 py-2.5 font-medium hover:bg-indigo-400 disabled:opacity-40"
          >
            {loading ? "AI 分析中…" : "开始拆解"}
          </button>
          <div className="mt-4 grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <select
                value={assetCategory}
                onChange={(e) => {
                  setAssetCategory(e.target.value);
                  setAssetSubcategory("");
                }}
                className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
              >
                {ASSET_CATEGORIES.map((item) => (
                  <option key={item.value} value={item.value}>
                    素材仓库：{item.label}
                  </option>
                ))}
              </select>
              <select
                value={assetSubcategory}
                onChange={(e) => setAssetSubcategory(e.target.value)}
                className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
              >
                <option value="">选择二级品类</option>
                {categoryByValue(assetCategory).subcategories.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </div>
            <p className="text-xs text-gray-500">
              将按“{categoryByValue(assetCategory).label}”重点拆解：
              {categoryByValue(assetCategory).note}
            </p>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
            >
              <option value="company_published">公司已发布优秀作品</option>
              <option value="external_reference">外部优秀案例</option>
              <option value="unused_internal">未采用参考方案</option>
            </select>
            <input
              value={productCategory}
              onChange={(e) => setProductCategory(e.target.value)}
              placeholder="产品分类，如：吸奶器"
              className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
            />
            <input
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="原始来源链接（外部案例建议填写）"
              className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
            />
            <input
              value={rightsNote}
              onChange={(e) => setRightsNote(e.target.value)}
              placeholder="使用说明，如：仅限内部参考"
              className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
            />
          </div>
          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        </Card>

        <div className="space-y-4">
          {!result && (
            <Card>
              <p className="text-sm text-gray-500">
                分析结果会显示在这里：视觉风格、色彩体系、构图、光影、材质、设计规则与
                AI 绘图提示词。
              </p>
            </Card>
          )}

          {result && a && (
            <>
              <Card>
                <div className="text-lg font-semibold">{result.name}</div>
                <p className="mt-1 text-sm text-gray-400">{result.summary}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {result.tags.map((t) => (
                    <Tag key={t.id}>{t.name}</Tag>
                  ))}
                </div>
                <Link
                  href={`/cases/${result.id}`}
                  className="mt-4 inline-block text-sm text-indigo-400 hover:underline"
                >
                  查看完整案例卡 →
                </Link>
              </Card>

              {/* 拆解重心：排版 + 文字 优先 */}
              <div className="grid grid-cols-2 gap-4">
                <Card className="border-indigo-500/40">
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="rounded bg-indigo-500 px-1 py-0.5 text-[9px] font-semibold text-white">
                      重心
                    </span>
                    <span className="text-sm font-semibold text-gray-200">排版</span>
                  </div>
                  <div className="text-sm">{a.layout.layout_type}</div>
                  <p className="mt-1 text-xs text-gray-500">
                    {a.layout.grid_columns} · {a.layout.modules}
                  </p>
                  <p className="mt-0.5 text-xs text-gray-500">{a.layout.margins}</p>
                </Card>
                <Card className="border-indigo-500/40">
                  <div className="text-sm font-semibold text-gray-200">文字 / 字体</div>
                  <div className="mt-1 text-sm">{a.typography.text_ratio}</div>
                  <p className="mt-1 text-xs text-gray-500">{a.typography.font_tone}</p>
                </Card>
              </div>

              <Card>
                <div className="mb-2 text-sm font-semibold text-gray-300">色彩体系</div>
                <Swatches colors={a.color.palette} />
                <p className="mt-2 text-xs text-gray-500">{a.color.description}</p>
              </Card>

              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <div className="text-sm font-semibold text-gray-300">构图</div>
                  <div className="mt-1 text-sm">{a.composition.type}</div>
                  <p className="mt-1 text-xs text-gray-500">{a.composition.description}</p>
                </Card>
                <Card>
                  <div className="text-sm font-semibold text-gray-300">光影</div>
                  <div className="mt-1 text-sm">{a.light.type}</div>
                  <p className="mt-1 text-xs text-gray-500">{a.light.description}</p>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
