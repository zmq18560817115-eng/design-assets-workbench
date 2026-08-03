"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  LayoutBlueprint,
  LayoutBlueprintInput,
  LayoutModule,
} from "@/lib/api";
import { LayoutWireframe } from "@/components/layout-wireframe";
import { MODULE_TYPE_OPTIONS } from "@/lib/module-types";

const statusLabels = {
  ai_generated: "AI 已生成",
  corrected: "人工已校正",
  human_edited: "人工已校正",
  verified: "人工已确认",
};

function asInput(item: LayoutBlueprint): LayoutBlueprintInput {
  return {
    canvas_ratio: item.canvas_ratio,
    orientation: item.orientation,
    grid_columns: item.grid_columns,
    grid_rows: item.grid_rows,
    margins: { ...item.margins },
    alignment: item.alignment,
    reading_flow: item.reading_flow,
    focal_region: item.focal_region ? { ...item.focal_region } : null,
    information_density: item.information_density,
    text_image_ratio: item.text_image_ratio,
    module_count: item.modules_json.length,
    modules_json: item.modules_json.map((module) => ({ ...module })),
    layout_signature: item.layout_signature,
    review_status: item.review_status,
    model_name: item.model_name,
    prompt_version: item.prompt_version,
    editor: item.editor,
  };
}

const orientationLabels: Record<string, string> = {
  portrait: "竖版",
  landscape: "横版",
  square: "方形",
};

const densityLabels: Record<string, string> = {
  low: "低（留白较多）",
  medium: "中（信息适中）",
  high: "高（信息较多）",
};

const alignmentLabels: Record<string, string> = {
  left: "左对齐",
  center: "居中对齐",
  right: "右对齐",
  mixed: "混合对齐",
};

const readingFlowLabels: Record<string, string> = {
  "top-to-bottom": "从上到下",
  "left-to-right": "从左到右",
  "z-pattern": "Z 形浏览",
  "f-pattern": "F 形浏览",
};

export function LayoutBlueprintEditor({
  caseId,
  imageUrl = "",
  defaultReviewer = "",
}: {
  caseId: number;
  imageUrl?: string;
  defaultReviewer?: string;
}) {
  const [versions, setVersions] = useState<LayoutBlueprint[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<LayoutBlueprintInput | null>(null);
  const [editor, setEditor] = useState(defaultReviewer);
  const [patternName, setPatternName] = useState("");
  const [showLabels, setShowLabels] = useState(true);
  const [showFocalRegion, setShowFocalRegion] = useState(false);
  const [showOriginal, setShowOriginal] = useState(true);
  const [imageLoadError, setImageLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const selected = useMemo(
    () => versions.find((item) => item.id === selectedId) || versions[0],
    [selectedId, versions]
  );

  const selectVersion = (item: LayoutBlueprint) => {
    setSelectedId(item.id);
    setDraft(asInput(item));
    setMessage("");
  };

  const load = async () => {
    setLoading(true);
    try {
      const items = await api.layoutBlueprints(caseId);
      setVersions(items);
      if (items[0]) selectVersion(items[0]);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "读取排版骨架失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  useEffect(() => {
    if (defaultReviewer && !editor) setEditor(defaultReviewer);
  }, [defaultReviewer, editor]);

  const updateModule = (index: number, patch: Partial<LayoutModule>) => {
    if (!draft) return;
    const modules = draft.modules_json.map((module, moduleIndex) =>
      moduleIndex === index ? { ...module, ...patch } : module
    );
    setDraft({ ...draft, modules_json: modules, module_count: modules.length });
  };

  const addModule = () => {
    if (!draft) return;
    const index = draft.modules_json.length + 1;
    const modules = [
      ...draft.modules_json,
      {
        id: `module-${index}`,
        type: "body_text",
        x: 0.1,
        y: 0.8,
        width: 0.8,
        height: 0.1,
        priority: index,
        alignment: draft.alignment || "center",
        description: "新增信息模块",
        label: "辅助信息",
        importance: index,
        content_summary: "",
        confidence: 1,
      },
    ];
    setDraft({ ...draft, modules_json: modules, module_count: modules.length });
  };

  const removeModule = (index: number) => {
    if (!draft) return;
    const modules = draft.modules_json.filter((_, itemIndex) => itemIndex !== index);
    setDraft({ ...draft, modules_json: modules, module_count: modules.length });
  };

  const saveRevision = async () => {
    if (!selected || !draft || !editor.trim()) {
      setMessage("请填写校正人后再保存。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const created = await api.reviseLayoutBlueprint(selected.id, {
        ...draft,
        module_count: draft.modules_json.length,
        review_status: "corrected",
        editor: editor.trim(),
      });
      setVersions((items) => [created, ...items]);
      selectVersion(created);
      setMessage(`已保存为版本 v${created.version}，旧版本仍保留。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "保存校正失败");
    } finally {
      setSaving(false);
    }
  };

  const verify = async () => {
    if (!selected || !editor.trim()) {
      setMessage("请填写确认人后再确认。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const created = await api.verifyLayoutBlueprint(selected.id, editor.trim());
      setVersions((items) => [created, ...items]);
      selectVersion(created);
      setMessage(`版本 v${created.version} 已人工确认。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "确认失败");
    } finally {
      setSaving(false);
    }
  };

  const regenerate = async () => {
    setSaving(true);
    setMessage("");
    try {
      const created = await api.generateLayoutBlueprint(caseId);
      setVersions((items) => [created, ...items]);
      selectVersion(created);
      setMessage(`已根据现有拆解生成版本 v${created.version}。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "重新生成失败");
    } finally {
      setSaving(false);
    }
  };

  const createPattern = async () => {
    if (!selected || selected.review_status !== "verified") {
      setMessage("请先人工确认当前骨架，再沉淀为排版模式。");
      return;
    }
    if (!patternName.trim() || !editor.trim()) {
      setMessage("请填写模式名称和沉淀人。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const pattern = await api.createLayoutPattern({
        name: patternName.trim(),
        description: "从案例人工确认骨架沉淀的可复用排版模式",
        source_blueprint_ids: [selected.id],
        editor: editor.trim(),
      });
      setPatternName("");
      setMessage(`已沉淀为排版模式「${pattern.name}」v${pattern.version}。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "沉淀排版模式失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <section className="rounded-2xl border border-line bg-panel p-5 text-sm text-gray-400">
        正在读取标准化排版骨架…
      </section>
    );
  }

  if (!selected || !draft) {
    return (
      <section className="rounded-2xl border border-line bg-panel p-5">
        <h2 className="font-semibold">标准化排版骨架</h2>
        <p className="mt-2 text-sm text-gray-400">当前案例还没有排版骨架。</p>
        <button
          onClick={regenerate}
          disabled={saving}
          className="mt-4 rounded-lg bg-indigo-500 px-4 py-2 text-sm text-white"
        >
          生成首版骨架
        </button>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-indigo-500/30 bg-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold text-indigo-400">步骤 2 · 人工审核</div>
          <h2 className="mt-1 text-lg font-semibold">确认 AI 拆解是否正确</h2>
          <p className="mt-1 text-sm leading-6 text-gray-400">
            系统已完成初步识别。你只需对照原图检查模块框；发现错误时再拖动、缩放或修改。
          </p>
        </div>
        <div className="flex max-w-full flex-wrap gap-2">
          {versions.map((item) => (
            <button
              key={item.id}
              onClick={() => selectVersion(item)}
              className={`rounded-lg px-2.5 py-1.5 text-xs ${
                selected.id === item.id
                  ? "bg-indigo-500 text-white"
                  : "border border-line text-gray-400"
              }`}
            >
              v{item.version} · {statusLabels[item.review_status]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {[
          ["1", "对照原图", "检查产品、标题和卖点框"],
          ["2", "有错才修改", "拖动框体或调整模块类型"],
          ["3", "提交结论", "正确则确认，修改后保存"],
        ].map(([step, title, description]) => (
          <div key={step} className="rounded-xl border border-line bg-ink p-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500 text-xs text-white">{step}</span>
              {title}
            </div>
            <p className="mt-1 pl-8 text-xs leading-5 text-gray-400">{description}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(360px,0.95fr)_1.05fr]">
        <div>
          <div className="rounded-xl bg-[#f4f5f8] p-5">
            <LayoutWireframe
              blueprint={draft}
              showLabels={showLabels}
              showFocalRegion={showFocalRegion}
              className="max-w-[460px]"
              backgroundImageUrl={showOriginal ? imageUrl : ""}
              onBackgroundImageError={() => setImageLoadError(true)}
              onModuleChange={updateModule}
            />
          </div>
          {(!imageUrl || imageLoadError) && (
            <div className="mt-3 rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 text-xs leading-5 text-amber-200">
              原图暂未加载，当前只能看到拆解框。请先检查案例图片地址或重新导入原图，再执行最终确认。
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-400">
            <button type="button" onClick={() => setShowOriginal((value) => !value)}
              className="rounded-lg border border-line px-3 py-1.5">
              {showOriginal ? "隐藏原图，只看框体" : "显示原图并对照"}
            </button>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showLabels}
                onChange={(event) => setShowLabels(event.target.checked)}
              />
              显示模块标签
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showFocalRegion}
                onChange={(event) => setShowFocalRegion(event.target.checked)}
              />
              显示焦点区
            </label>
          </div>
          <div className="mt-3 rounded-xl border border-line p-3">
            <div className="text-xs font-semibold text-gray-300">颜色说明</div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400">
              <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-blue-600" />产品图</span>
              <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-green-600" />文字信息</span>
              <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-red-500" />其他模块</span>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-line p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">系统自动识别</h3>
                <p className="mt-1 text-xs text-gray-400">以下内容由系统生成，通常不需要你录入。</p>
              </div>
              <span className="rounded-full bg-indigo-500/15 px-2.5 py-1 text-[11px] text-indigo-300">无需填写</span>
            </div>
            <dl className="mt-3 grid gap-2 sm:grid-cols-2">
              {[
                ["画面方向", orientationLabels[draft.orientation] || draft.orientation],
                ["画布比例", draft.canvas_ratio],
                ["信息密度", densityLabels[draft.information_density] || draft.information_density],
                ["对齐方式", alignmentLabels[draft.alignment] || draft.alignment],
                ["阅读顺序", readingFlowLabels[draft.reading_flow] || draft.reading_flow],
                ["图文占比", `文字约 ${Math.round(draft.text_image_ratio * 100)}%`],
                ["模块数量", `${draft.modules_json.length} 个`],
                ["识别来源", `${selected.model_name} · ${selected.prompt_version}`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-ink px-3 py-2">
                  <dt className="text-[11px] text-gray-500">{label}</dt>
                  <dd className="mt-0.5 text-sm text-gray-200">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <details className="rounded-xl border border-line p-4">
            <summary className="cursor-pointer text-sm font-semibold">高级参数（仅识别错误时修改）</summary>
            <p className="mt-1 text-xs leading-5 text-gray-400">这些是系统内部排版参数，日常审核可以跳过。</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="画布比例">
              <input
                value={draft.canvas_ratio}
                onChange={(event) => setDraft({ ...draft, canvas_ratio: event.target.value })}
                className="field"
              />
            </Field>
            <Field label="方向">
              <select
                value={draft.orientation}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    orientation: event.target.value as LayoutBlueprintInput["orientation"],
                  })
                }
                className="field"
              >
                <option value="portrait">竖版</option>
                <option value="landscape">横版</option>
                <option value="square">方形</option>
              </select>
            </Field>
            <Field label="文字占比">
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={draft.text_image_ratio}
                onChange={(event) =>
                  setDraft({ ...draft, text_image_ratio: Number(event.target.value) })
                }
                className="field"
              />
            </Field>
            {[
              ["栅格列数", "grid_columns"],
              ["栅格行数", "grid_rows"],
            ].map(([label, key]) => (
              <Field key={key} label={label}>
                <input
                  type="number"
                  min="1"
                  value={draft[key as "grid_columns" | "grid_rows"]}
                  onChange={(event) =>
                    setDraft({ ...draft, [key]: Number(event.target.value) })
                  }
                  className="field"
                />
              </Field>
            ))}
            <Field label="信息密度">
              <input
                value={draft.information_density}
                onChange={(event) =>
                  setDraft({ ...draft, information_density: event.target.value })
                }
                className="field"
              />
            </Field>
            <Field label="对齐策略">
              <input
                value={draft.alignment}
                onChange={(event) => setDraft({ ...draft, alignment: event.target.value })}
                className="field"
              />
            </Field>
            <Field label="阅读动线" wide>
              <input
                value={draft.reading_flow}
                onChange={(event) => setDraft({ ...draft, reading_flow: event.target.value })}
                className="field"
              />
            </Field>
            </div>
          </details>

          <div className="rounded-xl border border-line p-4">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">需要你确认：模块框是否准确</h3>
                <p className="mt-1 text-xs leading-5 text-gray-400">重点检查产品、标题、卖点是否框对，有无遗漏或越界。</p>
              </div>
              <button onClick={addModule} className="rounded-lg border border-line px-3 py-1.5 text-xs">
                补充遗漏模块
              </button>
            </div>
            <div className="space-y-2">
              {draft.modules_json.map((module, index) => (
                <div key={`${module.id}-${index}`} className="rounded-xl border border-line bg-ink p-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <select
                      value={module.type}
                      onChange={(event) => updateModule(index, { type: event.target.value })}
                      className="rounded-lg border border-line bg-panel px-2 py-1.5 text-xs"
                    >
                      {!MODULE_TYPE_OPTIONS.some((option) => option.value === module.type) && (
                        <option value={module.type}>{module.type}（旧类型）</option>
                      )}
                      {MODULE_TYPE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <input
                      value={module.description}
                      onChange={(event) => updateModule(index, { description: event.target.value })}
                      placeholder="模块说明"
                      className="rounded-lg border border-line bg-panel px-2 py-1.5 text-xs"
                    />
                  </div>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] text-gray-500">精确坐标（通常无需修改）</summary>
                    <div className="mt-2 grid grid-cols-4 gap-1.5">
                      {(["x", "y", "width", "height"] as const).map((key) => (
                        <label key={key} className="text-[10px] text-gray-500">
                          {{ x: "左边距", y: "上边距", width: "宽度", height: "高度" }[key]}
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={module[key]}
                            onChange={(event) => updateModule(index, { [key]: Number(event.target.value) })}
                            className="mt-1 w-full rounded border border-line bg-panel px-1.5 py-1 text-xs text-white"
                          />
                        </label>
                      ))}
                    </div>
                  </details>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-[10px] text-gray-500">
                      ID：{module.id} · 优先级 {module.priority}
                    </span>
                    <button onClick={() => removeModule(index)} className="text-[10px] text-rose-400">
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-indigo-400/30 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">提交本次审核</h3>
                <p className="mt-1 text-xs text-gray-500">审核人是唯一必填项；系统识别正确时直接确认。</p>
              </div>
              <span className="rounded-full bg-rose-50 px-2 py-1 text-[11px] text-rose-600">需人工操作</span>
            </div>
            <Field label="审核人（必填）">
              <input
                value={editor}
                onChange={(event) => setEditor(event.target.value)}
                placeholder="例如：设计负责人张茗淇"
                className="field"
              />
            </Field>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <button onClick={verify} disabled={saving || !editor.trim() || !imageUrl || imageLoadError} className="rounded-lg bg-emerald-500 px-3 py-2.5 text-xs font-semibold text-white disabled:opacity-50">
                拆解正确，确认通过
              </button>
              <button onClick={saveRevision} disabled={saving || !editor.trim()} className="rounded-lg bg-indigo-500 px-3 py-2.5 text-xs font-semibold text-white disabled:opacity-50">
                我已修改，保存新版
              </button>
              <button onClick={regenerate} disabled={saving} className="rounded-lg border border-gray-300 px-3 py-2.5 text-xs text-gray-700 disabled:opacity-50">
                错误较多，重新分析
              </button>
            </div>
            {(!imageUrl || imageLoadError) && <p className="mt-2 text-xs text-rose-600">原图不可见，暂不能确认通过。</p>}
            {message && <p className="mt-3 text-xs leading-5 text-amber-300">{message}</p>}
          </div>

          <details className="rounded-xl border border-line p-4">
            <summary className="cursor-pointer text-sm font-semibold text-gray-300">后续操作：加入排版模式候选</summary>
            <p className="mt-1 text-[11px] leading-5 text-gray-500">
              这不是本次审核必填项。只有人工确认版本可以成为模式证据。
            </p>
            <div className="mt-3 flex gap-2">
              <input
                value={patternName}
                onChange={(event) => setPatternName(event.target.value)}
                placeholder="例如：竖版标题主视觉转化模式"
                className="field flex-1"
              />
              <button
                onClick={createPattern}
                disabled={saving || selected.review_status !== "verified"}
                className="mt-1 rounded-lg bg-ink px-4 py-2 text-xs text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                沉淀模式
              </button>
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`text-xs text-gray-400 ${wide ? "sm:col-span-2" : ""}`}>
      {label}
      {children}
    </label>
  );
}
