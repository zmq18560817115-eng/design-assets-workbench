"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, CaseBusinessUpdate, CaseOut, PageRole } from "@/lib/api";
import { LayoutBlueprintEditor } from "@/components/layout-blueprint-editor";
import { Tag } from "@/components/ui";

const PAGE_ROLES: PageRole[] = [
  "cover_hook", "problem_statement", "cause_explanation", "product_display",
  "function_explanation", "parameter_comparison", "usage_step",
  "service_assurance", "conclusion", "call_to_action", "other",
];

function BusinessFields({ item, onSaved }: { item: CaseOut; onSaved: (value: CaseOut) => void }) {
  const [form, setForm] = useState<CaseBusinessUpdate>({
    product_name: item.product_name,
    content_purpose: item.content_purpose,
    page_role: item.page_role,
    sequence_index: item.sequence_index,
    brief_ref: item.brief_ref,
    business_line: item.business_line,
    product_category: item.product_category,
    channel: item.channel,
    campaign_stage: item.campaign_stage,
  });
  const [saving, setSaving] = useState(false);
  const field = (name: keyof CaseBusinessUpdate, value: string | number | null) =>
    setForm((current) => ({ ...current, [name]: value }));
  return (
    <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
      <h2 className="text-lg font-semibold">业务字段</h2>
      <p className="mt-1 text-sm text-gray-500">人工修改会标记为 manual，不会自动改变审核状态。</p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {(["product_name","content_purpose","brief_ref","business_line","product_category","channel","campaign_stage"] as const).map((name) => (
          <label key={name} className="text-xs text-gray-500">
            {name}
            <input value={form[name]} onChange={(e) => field(name, e.target.value)}
              className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm" />
          </label>
        ))}
        <label className="text-xs text-gray-500">page_role
          <select value={form.page_role} onChange={(e) => field("page_role", e.target.value as PageRole)}
            className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm">
            {PAGE_ROLES.map((role) => <option key={role}>{role}</option>)}
          </select>
        </label>
        <label className="text-xs text-gray-500">sequence_index
          <input type="number" min={0} value={form.sequence_index ?? ""}
            onChange={(e) => field("sequence_index", e.target.value === "" ? null : Number(e.target.value))}
            className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm" />
        </label>
      </div>
      <button disabled={saving} onClick={() => {
        setSaving(true);
        api.updateCaseBusiness(item.id, form).then(onSaved).finally(() => setSaving(false));
      }} className="mt-4 rounded-xl bg-accent px-4 py-2 text-sm text-white disabled:opacity-50">
        {saving ? "保存中…" : "保存业务字段"}
      </button>
    </section>
  );
}

function ReviewPanel({ item, onSaved }: { item: CaseOut; onSaved: (value: CaseOut) => void }) {
  const [reviewer, setReviewer] = useState(item.reviewer);
  const [status, setStatus] = useState<"verified" | "company_recommended" | "rejected">("verified");
  const [notes, setNotes] = useState(item.review_notes);
  const [keep, setKeep] = useState("");
  const [avoid, setAvoid] = useState("");
  const [saving, setSaving] = useState(false);
  const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);
  return (
    <section className="rounded-3xl border border-line bg-white p-5 md:p-7">
      <h2 className="text-lg font-semibold">人工审核</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <input value={reviewer} onChange={(e) => setReviewer(e.target.value)}
          placeholder="审核人" className="rounded-xl border border-line px-3 py-2 text-sm" />
        <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}
          className="rounded-xl border border-line px-3 py-2 text-sm">
          <option value="verified">verified</option>
          <option value="company_recommended">company_recommended</option>
          <option value="rejected">rejected</option>
        </select>
        <textarea value={keep} onChange={(e) => setKeep(e.target.value)}
          placeholder="keep_reasons，每行一条" className="min-h-28 rounded-xl border border-line px-3 py-2 text-sm" />
        <textarea value={avoid} onChange={(e) => setAvoid(e.target.value)}
          placeholder="avoid_reasons，每行一条" className="min-h-28 rounded-xl border border-line px-3 py-2 text-sm" />
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="审核说明" className="min-h-24 rounded-xl border border-line px-3 py-2 text-sm md:col-span-2" />
      </div>
      <button disabled={saving || !reviewer.trim()} onClick={() => {
        setSaving(true);
        api.reviewCase(item.id, {
          reviewer, trust_status: status,
          review_decision: status === "rejected" ? "reject" : "",
          review_notes: notes,
          keep_reasons: lines(keep), avoid_reasons: lines(avoid),
        }).then(onSaved).finally(() => setSaving(false));
      }} className="mt-4 rounded-xl bg-ink px-4 py-2 text-sm text-white disabled:opacity-50">
        {saving ? "提交中…" : "提交人工审核"}
      </button>
    </section>
  );
}

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
        <Link href="/assets?tab=library" className="text-sm text-gray-500 hover:text-accent">
          ← 返回素材库
        </Link>
        <Link
          href="/assets?tab=import"
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

      <BusinessFields item={item} onSaved={setItem} />
      <LayoutBlueprintEditor caseId={item.id} />
      <ReviewPanel item={item} onSaved={setItem} />
    </div>
  );
}
