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

export function LayoutBlueprintEditor({ caseId, imageUrl = "" }: { caseId: number; imageUrl?: string }) {
  const [versions, setVersions] = useState<LayoutBlueprint[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<LayoutBlueprintInput | null>(null);
  const [editor, setEditor] = useState("");
  const [patternName, setPatternName] = useState("");
  const [showLabels, setShowLabels] = useState(true);
  const [showFocalRegion, setShowFocalRegion] = useState(false);
  const [showOriginal, setShowOriginal] = useState(true);
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
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-400">
            Layout blueprint
          </div>
          <h2 className="mt-1 text-lg font-semibold">排版低保真骨架校正</h2>
          <p className="mt-1 text-xs leading-5 text-gray-400">
            只用框体表达模块位置、大小和层级。坐标范围为 0～1，保存会新建版本。
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

      <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(300px,0.85fr)_1.15fr]">
        <div>
          <div className="rounded-xl bg-[#f4f5f8] p-5">
            <LayoutWireframe
              blueprint={draft}
              showLabels={showLabels}
              showFocalRegion={showFocalRegion}
              className="max-w-[460px]"
              backgroundImageUrl={showOriginal ? imageUrl : ""}
              onModuleChange={updateModule}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-400">
            <button type="button" onClick={() => setShowOriginal((value) => !value)}
              className="rounded-lg border border-line px-3 py-1.5">
              {showOriginal ? "切换为纯标注图" : "切换为原图叠加"}
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
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-400">
            <div>画布：{draft.canvas_ratio}</div>
            <div>方向：{draft.orientation}</div>
            <div>栅格：{draft.grid_columns} × {draft.grid_rows}</div>
            <div>模块：{draft.modules_json.length}</div>
            <div className="col-span-2">
              来源：{selected.model_name} · {selected.prompt_version}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">模块位置与比例</h3>
              <button onClick={addModule} className="rounded-lg border border-line px-3 py-1.5 text-xs">
                增加模块
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
                  <div className="mt-2 grid grid-cols-4 gap-1.5">
                    {(["x", "y", "width", "height"] as const).map((key) => (
                      <label key={key} className="text-[10px] text-gray-500">
                        {key}
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

          <div className="sticky bottom-3 z-20 rounded-xl border border-line bg-white/95 p-3 shadow-lg backdrop-blur">
            <Field label="校正／确认人">
              <input
                value={editor}
                onChange={(event) => setEditor(event.target.value)}
                placeholder="填写设计师姓名"
                className="field"
              />
            </Field>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button onClick={saveRevision} disabled={saving} className="rounded-lg bg-indigo-500 px-3 py-2 text-xs text-white disabled:opacity-50">
                保存校正
              </button>
              <button onClick={verify} disabled={saving} className="rounded-lg bg-emerald-500 px-3 py-2 text-xs text-white disabled:opacity-50">
                确认此版
              </button>
              <button onClick={regenerate} disabled={saving} className="rounded-lg border border-line px-3 py-2 text-xs disabled:opacity-50">
                重新生成
              </button>
            </div>
            {message && <p className="mt-3 text-xs leading-5 text-amber-300">{message}</p>}
          </div>

          <div className="rounded-xl border border-line p-3">
            <div className="text-xs font-semibold text-gray-300">沉淀到排版模式库</div>
            <p className="mt-1 text-[11px] leading-5 text-gray-500">
              只有人工确认版本可以成为模式证据，来源案例和骨架版本会自动保留。
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
          </div>
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
