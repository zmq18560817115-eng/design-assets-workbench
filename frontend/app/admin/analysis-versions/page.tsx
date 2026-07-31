"use client";

import { FormEvent, useEffect, useState } from "react";
import { AnalysisRuntimeVersion, analysisEvaluationApi } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

export default function AnalysisVersionsPage() {
  const [versions, setVersions] = useState<AnalysisRuntimeVersion[]>([]);
  const [message, setMessage] = useState("");
  const load = () => analysisEvaluationApi.versions().then(setVersions).catch((e) => setMessage(e.message));
  useEffect(() => {
    void analysisEvaluationApi.versions().then(setVersions).catch((e) => setMessage(e.message));
  }, []);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      await analysisEvaluationApi.createVersion({
        model_name: data.get("model_name"), model_provider: data.get("model_provider"),
        prompt_version: data.get("prompt_version"), prompt_text: data.get("prompt_text"),
        validator_version: data.get("validator_version"), validator_config: {},
        created_by: data.get("created_by"),
      }); event.currentTarget.reset(); setMessage("新版本已创建，旧版本保持不变"); load();
    } catch (error) { setMessage((error as Error).message); }
  };
  return <div className="space-y-7"><div><h1 className="text-3xl font-semibold">Prompt 与校验版本</h1>
    <p className="mt-2 text-sm text-gray-500">版本只新增、不覆盖；冻结后作为 Holdout 的唯一执行快照。</p></div>
    <Card><form onSubmit={create} className="grid gap-3 md:grid-cols-2">
      {["model_provider","model_name","prompt_version","validator_version","created_by"].map((name) =>
        <input key={name} name={name} required placeholder={name} className="rounded-xl border border-line px-3 py-2 text-sm" />)}
      <textarea name="prompt_text" placeholder="Prompt 草稿" className="min-h-24 rounded-xl border border-line px-3 py-2 text-sm md:col-span-2" />
      <button className="rounded-xl bg-ink px-4 py-2 text-sm text-white md:col-span-2">创建新版本</button>
    </form>{message && <p className="mt-3 text-sm">{message}</p>}</Card>
    <div className="grid gap-4 md:grid-cols-2">{versions.map((item) => <Card key={item.id}>
      <div className="flex justify-between"><b>{item.prompt_version}</b><span className="text-xs text-accent">{item.status}</span></div>
      <p className="mt-2 text-sm">{item.model_provider} · {item.model_name}</p>
      <p className="mt-1 text-xs text-gray-500">{item.validator_version}</p>
    </Card>)}</div></div>;
}
