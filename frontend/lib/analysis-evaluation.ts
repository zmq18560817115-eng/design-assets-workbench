export type DatasetState =
  | "draft" | "gt_ready" | "calibration_active" | "blocked_by_provider_availability" | "calibration_passed"
  | "version_frozen" | "holdout_ready" | "holdout_running"
  | "passed" | "failed" | "consumed";

export interface AnalysisDatasetItem {
  id: number;
  case_id: number;
  dataset_split: "calibration" | "holdout";
  gt_status: "pending" | "ready";
  reviewer: string;
  reason: string;
  ground_truth?: Record<string, unknown>;
}

export interface AnalysisDataset {
  id: number;
  dataset_version: string;
  name: string;
  product_category: string;
  description: string;
  status: DatasetState;
  sealed: boolean;
  consumed: boolean;
  counts: { calibration: number; holdout: number };
  items: AnalysisDatasetItem[];
  created_by: string;
  created_at: string;
}

export interface AnalysisRuntimeVersion {
  id: number;
  model_name: string;
  model_provider: string;
  prompt_version: string;
  prompt_hash: string;
  validator_version: string;
  validator_hash: string;
  status: "draft" | "calibration_passed" | "frozen" | "holdout_passed" | "deprecated";
  created_by: string;
  created_at: string;
  frozen_at: string | null;
}

export interface AnalysisEvaluationRun {
  id: number;
  dataset_id: number;
  dataset_split: "calibration" | "holdout";
  run_status: "queued" | "running" | "passed" | "failed";
  aggregate: Record<string, number>;
  version_snapshot: Partial<AnalysisRuntimeVersion>;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number;
  unsealed: boolean;
  results?: {
    id: number; item_id: number; status: string; error_code: string;
    metrics: Record<string, number>; prediction: Record<string, unknown>;
  }[];
}

export type ProviderStage = "provider_probe" | "smoke" | "canary" | "full";

export interface ProviderWorkflowStatus {
  status: "blocked_by_provider_availability" | "calibration_in_progress" | "calibration_ready_for_freeze";
  configuration: {
    provider: string; api_key: "configured" | "missing"; base_url: string;
    region: string; model: string; batch_concurrency: number;
    timeouts: { connect_seconds: number; read_seconds: number };
    calibration: {
      read_timeout_seconds: number; max_tokens: number; image_edge: number;
      stream: boolean; retry_read_timeout: boolean;
    };
    max_retries: number; configuration_errors: string[];
  };
  gates: Record<string, boolean>;
  execution: {
    running: boolean; stage: string; started_at: string | null;
    finished_at: string | null; exit_code: number | null; message: string;
  };
  actions: Record<ProviderStage | "holdout", boolean>;
  reports: Record<ProviderStage, Record<string, unknown>>;
  holdout: { sealed: boolean; executed: boolean; message: string };
}

const adminHeaders = {
  "Content-Type": "application/json",
  "X-Workbench-Role": "admin",
};

async function read<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(body.detail || `请求失败 ${response.status}`);
  }
  return response.json();
}

export const analysisEvaluationApi = {
  providerStatus: () =>
    fetch("/api/admin/provider-availability", {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<ProviderWorkflowStatus>(response)),
  runProviderStage: (stage: ProviderStage) =>
    fetch("/api/admin/provider-availability/run", {
      method: "POST", headers: adminHeaders, body: JSON.stringify({ stage }),
    }).then((response) => read<ProviderWorkflowStatus>(response)),
  datasets: () =>
    fetch("/api/analysis-evaluation/datasets", {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisDataset[]>(response)),
  dataset: (version: string) =>
    fetch(`/api/analysis-evaluation/datasets/${encodeURIComponent(version)}`, {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisDataset>(response)),
  createDataset: (payload: Record<string, unknown>) =>
    fetch("/api/analysis-evaluation/datasets", {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisDataset>(response)),
  assignItem: (version: string, payload: Record<string, unknown>) =>
    fetch(`/api/analysis-evaluation/datasets/${encodeURIComponent(version)}/items`, {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisDatasetItem>(response)),
  saveGroundTruth: (version: string, itemId: string | number, payload: Record<string, unknown>) =>
    fetch(`/api/analysis-evaluation/datasets/${encodeURIComponent(version)}/items/${itemId}/ground-truth`, {
      method: "PUT", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisDatasetItem>(response)),
  versions: () =>
    fetch("/api/analysis-versions", {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisRuntimeVersion[]>(response)),
  createVersion: (payload: Record<string, unknown>) =>
    fetch("/api/analysis-versions", {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisRuntimeVersion>(response)),
  freezeVersion: (payload: Record<string, unknown>) =>
    fetch("/api/analysis-versions/freeze", {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<Record<string, unknown>>(response)),
  runs: () =>
    fetch("/api/analysis-evaluation/runs", {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisEvaluationRun[]>(response)),
  run: (id: string | number) =>
    fetch(`/api/analysis-evaluation/runs/${id}`, {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisEvaluationRun>(response)),
  execute: (payload: Record<string, unknown>) =>
    fetch("/api/analysis-evaluation/runs", {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisEvaluationRun>(response)),
  unseal: (id: string | number, actor: string) =>
    fetch(`/api/analysis-evaluation/runs/${id}/unseal`, {
      method: "POST", headers: adminHeaders,
      body: JSON.stringify({ actor, confirm_consumed: true }),
    }).then((response) => read<AnalysisEvaluationRun>(response)),
  retryResult: (id: string | number, actor: string) =>
    fetch(`/api/analysis-evaluation/results/${id}/retry`, {
      method: "POST", headers: adminHeaders, body: JSON.stringify({ actor }),
    }).then((response) => read<Record<string, unknown>>(response)),
};
