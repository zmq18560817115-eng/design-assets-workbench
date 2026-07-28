"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card } from "@/components/ui";

type Status = {
  total: number;
  done: number;
  failed: number;
  skipped: number;
  status: string;
  case_ids: number[];
  errors: string[];
  skipped_files: string[];
  concurrency: number;
};

export default function BatchPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [batchId, setBatchId] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sourceType, setSourceType] = useState("external_reference");
  const [productCategory, setProductCategory] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  const start = async () => {
    if (files.length === 0) return;
    setSubmitting(true);
    setStatus(null);
    try {
      const r = await api.analyzeBatch(files, {
        source_type: sourceType,
        product_category: productCategory,
        rights_note: sourceType === "external_reference" ? "仅限内部设计参考" : "",
      });
      setBatchId(r.batch_id);
      timer.current = setInterval(async () => {
        try {
          const s = await api.batchStatus(r.batch_id);
          setStatus(s);
          if (s.status === "completed" && timer.current) {
            clearInterval(timer.current);
            timer.current = null;
          }
        } catch {
          /* ignore transient */
        }
      }, 1500);
    } finally {
      setSubmitting(false);
    }
  };

  const processed = status ? status.done + status.failed + status.skipped : 0;
  const pct = status && status.total ? Math.round((processed / status.total) * 100) : 0;

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">批量上传</h1>
      <p className="mb-6 text-sm text-gray-400">
        一次选择多张同类型案例图片，系统在后台顺序拆解并入库，可离开页面稍后再回来查看。
        开启视觉大模型时每张较慢（约 1~2 分钟），适合放着批量沉淀素材。
      </p>

      <Card>
        <label className="flex h-40 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-line hover:border-indigo-500">
          <span className="text-sm text-gray-400">
            {files.length > 0 ? `已选择 ${files.length} 张` : "点击选择多张图片 · 可多选"}
          </span>
          <input
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
          />
        </label>

        {files.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {files.slice(0, 24).map((f, i) => (
              <span
                key={i}
                className="max-w-[140px] truncate rounded bg-ink px-2 py-1 text-xs text-gray-400"
              >
                {f.name}
              </span>
            ))}
            {files.length > 24 && (
              <span className="px-2 py-1 text-xs text-gray-500">
                +{files.length - 24}…
              </span>
            )}
          </div>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
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
            placeholder="本批次产品分类，如：吸奶器"
            className="rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-gray-700"
          />
        </div>

        <button
          onClick={start}
          disabled={submitting || files.length === 0 || (!!status && status.status !== "completed")}
          className="mt-4 w-full rounded-lg bg-indigo-500 py-2.5 font-medium hover:bg-indigo-400 disabled:opacity-40"
        >
          {submitting
            ? "提交中…"
            : status && status.status !== "completed"
            ? "拆解进行中…"
            : `开始批量拆解（${files.length} 张）`}
        </button>
      </Card>

      {status && (
        <Card className="mt-6">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-semibold text-gray-200">
              {status.status === "completed" ? "已完成" : "拆解中…"}
            </span>
            <span className="text-gray-400">
              {processed}/{status.total} · 成功 {status.done} · 跳过重复 {status.skipped}
              {status.failed > 0 && ` · 失败 ${status.failed}`}
              {status.concurrency ? ` · 并发 ${status.concurrency}` : ""}
            </span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded bg-ink">
            <div
              className="h-3 rounded bg-indigo-500 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>

          {status.case_ids.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-xs text-gray-500">已生成案例</div>
              <div className="flex flex-wrap gap-2">
                {status.case_ids.map((id) => (
                  <Link
                    key={id}
                    href={`/cases/${id}`}
                    className="rounded bg-panel px-2 py-1 text-xs text-indigo-400 hover:underline"
                  >
                    #{id}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {status.skipped_files.length > 0 && (
            <div className="mt-3 text-xs text-gray-500">
              跳过的近重复：{status.skipped_files.slice(0, 8).join("、")}
              {status.skipped_files.length > 8 && ` 等 ${status.skipped_files.length} 张`}
            </div>
          )}

          {status.errors.length > 0 && (
            <div className="mt-3 text-xs text-red-400">
              {status.errors.slice(0, 5).map((e, i) => (
                <div key={i}>{e}</div>
              ))}
            </div>
          )}

          {status.status === "completed" && (
            <div className="mt-4 flex gap-3 text-sm">
              <Link href="/cases" className="text-indigo-400 hover:underline">
                查看案例库 →
              </Link>
              <Link href="/concept" className="text-indigo-400 hover:underline">
                查看设计概论 →
              </Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
