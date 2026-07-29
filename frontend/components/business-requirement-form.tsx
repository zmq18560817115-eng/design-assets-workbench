"use client";

import { BusinessRequirementCreate, api } from "@/lib/api";
import { useMemo, useState } from "react";

export const emptyRequirement: BusinessRequirementCreate = {
  title: "", request_text: "", industry: "", product_category: "", channel: "",
  canvas_ratio: "3:4", orientation: "portrait", campaign_stage: "",
  business_goal: "", target_audience: "", key_message: "", mandatory_elements: [],
  information_density: "medium", reference_case_ids: [], created_by: "",
  content_purpose: "", required_modules_json: [], optional_modules_json: [],
  forbidden_modules_json: [], selling_points_json: [], style_keywords_json: [],
  raw_requirement: "", reference_case_ids_json: [], reference_image_path: "",
  creator: "", status: "draft",
};

const moduleTypes = [
  "main_title", "subtitle", "body_text", "product_image", "person_image",
  "scene_image", "selling_point", "feature_list", "parameter_table", "price",
  "logo", "cta", "footnote", "decoration", "background", "other",
];

export function BusinessRequirementForm({
  value,
  onSubmit,
  submitLabel,
  disabled = false,
}: {
  value: BusinessRequirementCreate;
  onSubmit: (value: BusinessRequirementCreate) => Promise<void>;
  submitLabel: string;
  disabled?: boolean;
}) {
  const [form, setForm] = useState(value);
  const [message, setMessage] = useState("");
  const conflict = useMemo(
    () => form.required_modules_json.filter((item) => form.forbidden_modules_json.includes(item)),
    [form.required_modules_json, form.forbidden_modules_json]
  );
  const set = <K extends keyof BusinessRequirementCreate>(
    key: K,
    next: BusinessRequirementCreate[K]
  ) => setForm((current) => ({ ...current, [key]: next }));
  const toggle = (
    key: "required_modules_json" | "optional_modules_json" | "forbidden_modules_json",
    item: string
  ) => {
    const values = form[key];
    set(key, values.includes(item) ? values.filter((value) => value !== item) : [...values, item]);
  };
  const csv = (value: string) =>
    value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);

  return (
    <form
      className="space-y-6"
      onSubmit={async (event) => {
        event.preventDefault();
        if (conflict.length) {
          setMessage(`必需模块与禁止模块冲突：${conflict.join("、")}`);
          return;
        }
        setMessage("");
        await onSubmit({
          ...form,
          request_text: form.raw_requirement,
          reference_case_ids: form.reference_case_ids_json,
          created_by: form.creator,
        });
      }}
    >
      <Section title="基础任务信息">
        <Input label="需求标题" value={form.title} onChange={(v) => set("title", v)} required />
        <Input label="创建人" value={form.creator} onChange={(v) => set("creator", v)} />
        <TextArea label="原始需求" value={form.raw_requirement} onChange={(v) => set("raw_requirement", v)} />
      </Section>
      <Section title="产品、渠道与内容目的">
        <Input label="产品品类" value={form.product_category} onChange={(v) => set("product_category", v)} />
        <Select label="渠道" value={form.channel} onChange={(v) => set("channel", v)}
          options={["小红书","电商详情","产品海报","社交媒体","活动宣传","内部提案","其他"]} />
        <Select label="内容目的" value={form.content_purpose} onChange={(v) => set("content_purpose", v)}
          options={["产品介绍","卖点说明","参数对比","上新宣传","活动促销","品牌表达","使用教程","用户教育","其他"]} />
        <Input label="目标人群" value={form.target_audience} onChange={(v) => set("target_audience", v)} />
        <Input label="画布比例" value={form.canvas_ratio} onChange={(v) => set("canvas_ratio", v)} />
        <Select label="信息密度" value={form.information_density} onChange={(v) => set("information_density", v as BusinessRequirementCreate["information_density"])}
          options={["low","medium","high"]} />
      </Section>
      <Section title="模块条件">
        <div className="col-span-full grid gap-3 lg:grid-cols-3">
          {(["required_modules_json","optional_modules_json","forbidden_modules_json"] as const).map((key) => (
            <div key={key} className="rounded-xl border border-line p-3">
              <div className="mb-2 text-sm font-semibold">
                {key === "required_modules_json" ? "必需模块" : key === "optional_modules_json" ? "可选模块" : "禁止模块"}
              </div>
              <div className="flex flex-wrap gap-2">
                {moduleTypes.map((item) => (
                  <button type="button" key={item} onClick={() => toggle(key, item)}
                    className={`rounded-full border px-2.5 py-1 text-xs ${form[key].includes(item) ? "border-accent bg-lilac text-accent" : "border-line"}`}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        {conflict.length > 0 && <p className="col-span-full text-sm text-red-500">冲突：{conflict.join("、")}</p>}
      </Section>
      <Section title="内容补充与参考">
        <TextArea label="核心卖点（逗号或换行分隔）" value={form.selling_points_json.join("，")} onChange={(v) => set("selling_points_json", csv(v))} />
        <TextArea label="风格关键词（逗号或换行分隔）" value={form.style_keywords_json.join("，")} onChange={(v) => set("style_keywords_json", csv(v))} />
        <Input label="参考案例 ID（逗号分隔）" value={form.reference_case_ids_json.join(",")} onChange={(v) => set("reference_case_ids_json", csv(v).map(Number).filter(Number.isInteger))} />
        <label className="text-sm text-gray-600">参考图片
          <input type="file" accept="image/*" className="mt-2 block w-full text-sm"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              try {
                const result = await api.uploadRequirementReference(file);
                set("reference_image_path", result.path);
                setMessage("参考图片已上传。");
              } catch (cause) {
                setMessage(cause instanceof Error ? cause.message : "参考图片上传失败");
              }
            }} />
          {form.reference_image_path && <span className="mt-1 block text-xs text-gray-400">{form.reference_image_path}</span>}
        </label>
      </Section>
      {message && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-700">{message}</p>}
      <button disabled={disabled || Boolean(conflict.length)} className="rounded-xl bg-ink px-6 py-3 text-sm text-white disabled:opacity-40">
        {submitLabel}
      </button>
    </form>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-line bg-white p-5">
    <h2 className="mb-4 text-lg font-bold">{title}</h2>
    <div className="grid gap-4 md:grid-cols-2">{children}</div>
  </section>;
}
function Input({ label, value, onChange, required=false }: { label:string; value:string; onChange:(value:string)=>void; required?:boolean }) {
  return <label className="text-sm text-gray-600">{label}<input required={required} value={value} onChange={(e)=>onChange(e.target.value)} className="field" /></label>;
}
function TextArea({ label, value, onChange }: { label:string; value:string; onChange:(value:string)=>void }) {
  return <label className="text-sm text-gray-600">{label}<textarea value={value} onChange={(e)=>onChange(e.target.value)} rows={4} className="field" /></label>;
}
function Select({ label, value, onChange, options }: { label:string; value:string; onChange:(value:string)=>void; options:string[] }) {
  return <label className="text-sm text-gray-600">{label}<select value={value} onChange={(e)=>onChange(e.target.value)} className="field"><option value="">请选择</option>{options.map((item)=><option key={item}>{item}</option>)}</select></label>;
}
