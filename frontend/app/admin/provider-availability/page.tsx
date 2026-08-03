"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { analysisEvaluationApi, ProviderStage, ProviderWorkflowStatus } from "@/lib/analysis-evaluation";
import { Card } from "@/components/ui";

const stages: { key: ProviderStage; title: string; description: string }[] = [
  { key: "provider_probe", title: "单张正式预检", description: "依次检查配置、网络、最小文本、最小图片和单张正式 Schema。" },
  { key: "smoke", title: "连续 3 次冒烟", description: "三次最小文本与最小图片请求必须全部成功。" },
  { key: "canary", title: "3 张 Calibration Canary", description: "简单、中等、复杂各一张；调用、Schema 与业务质量门禁必须全部通过，禁止 fallback。" },
  { key: "full", title: "24 张完整 Calibration", description: "成功率至少 95%，Schema 和坐标合法率必须为 100%。" },
];

const gateLabels: Record<string, string> = {
  formal_schema_ready: "单张正式 Schema 成功",
  smoke_three_ready: "连续 3 次冒烟成功",
  canary_three_ready: "3 张 Canary 成功",
  full_calibration_ready: "24 张 Calibration 达标",
  holdout_frozen: "版本已经冻结",
};

type ProbeResult = { status?: string; error_type?: string; http_status?: number; request_id?: string; total_ms?: number };

function latestProbe(status: ProviderWorkflowStatus): Record<string, ProbeResult> {
  const report = status.reports.provider_probe as { runs?: unknown[] };
  const run = Array.isArray(report?.runs) ? report.runs.at(-1) : null;
  return run && typeof run === "object" ? run as Record<string, ProbeResult> : {};
}

export default function ProviderAvailabilityPage() {
  const [status, setStatus] = useState<ProviderWorkflowStatus | null>(null);
  const [message, setMessage] = useState("");
  const load = useCallback(() => {
    analysisEvaluationApi.providerStatus().then(setStatus).catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!status?.execution.running) return;
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [status?.execution.running, load]);

  async function run(stage: ProviderStage) {
    if (!window.confirm("确认执行当前最小阶段？系统会严格遵守门禁，不会运行 Holdout。")) return;
    setMessage("");
    try { setStatus(await analysisEvaluationApi.runProviderStage(stage)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "启动失败"); }
  }

  if (!status) return <Card>{message || "正在读取模型服务状态…"}</Card>;
  const config = status.configuration;
  const probe = latestProbe(status);
  return <div className="space-y-8">
    <header>
      <Link href="/admin/analysis-evaluation" className="text-sm text-gray-500">← AI 拆解校准</Link>
      <h1 className="mt-3 text-3xl font-semibold">模型服务诊断与恢复</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-500">严格按正式预检、三次冒烟、三张 Canary、完整 Calibration 推进；任一门禁失败立即停止。</p>
    </header>

    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="font-semibold">当前状态</h2><p className="mt-1 text-sm text-gray-500">{status.status}</p></div>
        <span className={`rounded-full px-3 py-1 text-xs ${status.status === "blocked_by_provider_availability" ? "bg-rose-50 text-rose-700" : status.status === "calibration_in_progress" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{status.status === "blocked_by_provider_availability" ? "服务阻断" : status.status === "calibration_in_progress" ? "校准进行中" : "可以冻结候选版本"}</span>
      </div>
      <div className="mt-5 grid gap-3 text-sm md:grid-cols-2 lg:grid-cols-4">
        <div><span className="text-gray-500">Provider</span><div>{config.provider}</div></div>
        <div><span className="text-gray-500">区域</span><div>{config.region}</div></div>
        <div><span className="text-gray-500">部署点</span><div className="break-all">{config.model}</div></div>
        <div><span className="text-gray-500">API Key</span><div>{config.api_key}</div></div>
        <div><span className="text-gray-500">连接 / 读取超时</span><div>{config.timeouts.connect_seconds}s / {config.timeouts.read_seconds}s</div></div>
        <div><span className="text-gray-500">最大重试</span><div>{config.max_retries}</div></div>
        <div><span className="text-gray-500">并发</span><div>{config.batch_concurrency}</div></div>
        <div><span className="text-gray-500">Holdout</span><div>{status.holdout.sealed ? "保持封存" : "异常"}</div></div>
        <div><span className="text-gray-500">正式调用方式</span><div>{config.calibration.stream ? "流式接收" : "非流式"}</div></div>
        <div><span className="text-gray-500">正式输出上限</span><div>{config.calibration.max_tokens} tokens</div></div>
        <div><span className="text-gray-500">正式图片边长</span><div>{config.calibration.image_edge}px</div></div>
        <div><span className="text-gray-500">正式读取超时</span><div>{config.calibration.read_timeout_seconds}s</div></div>
      </div>
    </Card>

    <section className="grid gap-4 lg:grid-cols-2">
      <Card><h2 className="font-semibold">恢复门禁</h2><div className="mt-4 space-y-2">{Object.entries(status.gates).map(([key, passed]) => <div key={key} className="flex justify-between rounded-xl bg-gray-50 p-3 text-sm"><span>{gateLabels[key] || key}</span><span className={passed ? "text-emerald-700" : "text-rose-700"}>{passed ? "通过" : "未通过"}</span></div>)}</div></Card>
      <Card><h2 className="font-semibold">当前运行</h2><div className="mt-4 break-words text-sm leading-7"><p>状态：{status.execution.running ? "运行中" : "空闲"}</p><p>阶段：{status.execution.stage || "—"}</p><p>结果：{status.execution.message || "—"}</p><p>退出码：{status.execution.exit_code ?? "—"}</p></div></Card>
    </section>

    {Object.keys(probe).length > 0 && <Card><h2 className="font-semibold">最近一次正式预检</h2><div className="mt-4 grid gap-3 text-sm md:grid-cols-3">{["minimal_text", "minimal_image", "formal_schema"].map((key) => {
      const result = probe[key] || {};
      return <div key={key} className="rounded-xl bg-gray-50 p-4"><div className="font-medium">{key}</div><div className={result.status === "success" ? "mt-2 text-emerald-700" : "mt-2 text-rose-700"}>{result.status || "未执行"}</div><div className="mt-1 text-xs leading-5 text-gray-500">HTTP {result.http_status ?? "—"} · {result.total_ms ?? "—"} ms</div>{result.error_type && <div className="text-xs text-rose-600">{result.error_type}</div>}{result.request_id && <div className="break-all text-xs text-gray-500">请求：{result.request_id}</div>}</div>;
    })}</div></Card>}

    <section className="grid gap-4 lg:grid-cols-2">{stages.map((stage, index) => <Card key={stage.key}><div className="text-xs text-accent">步骤 {index + 1}</div><h2 className="mt-2 font-semibold">{stage.title}</h2><p className="mt-2 text-sm text-gray-500">{stage.description}</p><button disabled={!status.actions[stage.key]} onClick={() => run(stage.key)} className="mt-5 rounded-xl bg-ink px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-35">{status.execution.running && status.execution.stage === stage.key ? "运行中…" : "执行当前阶段"}</button></Card>)}</section>
    {message && <p className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{message}</p>}
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{status.holdout.message}。系统没有提供从此页面执行 Holdout 的按钮。</div>
  </div>;
}
