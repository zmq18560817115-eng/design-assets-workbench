export type DatasetState =
  | "draft" | "gt_ready" | "calibration_active" | "calibration_passed"
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
  versions: () =>
    fetch("/api/analysis-versions", {
      cache: "no-store", headers: adminHeaders,
    }).then((response) => read<AnalysisRuntimeVersion[]>(response)),
  createVersion: (payload: Record<string, unknown>) =>
    fetch("/api/analysis-versions", {
      method: "POST", headers: adminHeaders, body: JSON.stringify(payload),
    }).then((response) => read<AnalysisRuntimeVersion>(response)),
};
