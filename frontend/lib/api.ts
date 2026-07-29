// 后端 API 封装。开发时通过 next.config.js 的 rewrites 代理到 FastAPI。

export interface TagOut {
  id: number;
  name: string;
  category: string;
}

export interface ImageOut {
  id: number;
  url: string;
  filename: string;
  source: string;
  source_type: string;
  source_url: string;
  rights_note: string;
  visibility: string;
  uploader: string;
}

export interface AnalysisData {
  color: { palette: string[]; primary: string; description: string };
  composition: { type: string; description: string };
  light: { type: string; description: string };
  layout: {
    layout_type: string;
    alignment: string;
    hierarchy: string[];
    whitespace: string;
    focal: string;
    grid_columns: string;
    modules: string;
    margins: string;
    spacing: string;
    content_ratio: string;
    grid_metrics: Record<string, number>;
    description: string;
  };
  typography: {
    title_treatment: string;
    font_tone: string;
    size_contrast: string;
    pairing: string;
    text_ratio: string;
    description: string;
  };
  style: { style_tags: string[]; mood_keywords: string[]; brand_position: string };
  design_rules: { why_good: string[]; reusable_methods: string[] };
  insights: {
    target_audience: string;
    applicable_scenes: string[];
    color_roles: string[];
    composition_principles: string[];
    emotion_narrative: string;
    critique: string[];
    improvement: string[];
  } | null;
  analyzed_by: string;
  version: number;
  confidence: number;
  model_name: string;
  prompt_version: string;
  review_status: string;
  material: string;
  prompt: string;
}

export interface CaseOut {
  id: number;
  project_id: number | null;
  name: string;
  content_type: string;
  product_category: string;
  asset_category: string;
  asset_subcategory: string;
  industry: string;
  scene: string;
  summary: string;
  business_line: string;
  channel: string;
  campaign_stage: string;
  business_goal: string;
  review_decision: string;
  review_notes: string;
  reviewer: string;
  reviewed_at: string | null;
  trust_status: string;
  status: string;
  created_at: string;
  image: ImageOut | null;
  tags: TagOut[];
  analysis: AnalysisData | null;
}

export interface NormalizedRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LayoutMargins {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface LayoutModule extends NormalizedRegion {
  id: string;
  type: string;
  priority: number;
  alignment: string;
  description: string;
}

export interface LayoutBlueprintInput {
  canvas_ratio: string;
  orientation: "portrait" | "landscape" | "square";
  grid_columns: number;
  grid_rows: number;
  margins: LayoutMargins;
  alignment: string;
  reading_flow: string;
  focal_region: NormalizedRegion | null;
  information_density: string;
  text_image_ratio: number;
  module_count: number;
  modules_json: LayoutModule[];
  review_status: "ai_unverified" | "human_edited" | "verified";
  model_name: string;
  prompt_version: string;
  editor: string;
}

export interface LayoutBlueprint extends LayoutBlueprintInput {
  id: number;
  case_id: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface LayoutPattern extends LayoutBlueprintInput {
  id: number;
  name: string;
  description: string;
  source_blueprint_ids: number[];
  source_case_ids: number[];
  industry_tags: string[];
  scene_tags: string[];
  channel_tags: string[];
  business_goal_tags: string[];
  usage_notes: string;
  version: number;
  review_status: "human_edited" | "verified";
  created_at: string;
  updated_at: string;
}

export interface LayoutPatternCreate {
  name: string;
  description?: string;
  source_blueprint_ids: number[];
  industry_tags?: string[];
  scene_tags?: string[];
  channel_tags?: string[];
  business_goal_tags?: string[];
  usage_notes?: string;
  editor: string;
}

export interface BusinessRequirementCreate {
  title: string;
  request_text: string;
  industry: string;
  product_category: string;
  channel: string;
  canvas_ratio: string;
  orientation: "" | "portrait" | "landscape" | "square";
  campaign_stage: string;
  business_goal: string;
  target_audience: string;
  key_message: string;
  mandatory_elements: string[];
  information_density: "" | "low" | "medium" | "high";
  reference_case_ids: number[];
  created_by: string;
  status: "draft" | "ready" | "archived";
}

export interface BusinessRequirement extends BusinessRequirementCreate {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface BusinessRequirementMatch {
  requirement: BusinessRequirement;
  pattern_matches: {
    pattern: LayoutPattern;
    score: number;
    reasons: string[];
  }[];
  case_matches: {
    case_id: number;
    name: string;
    blueprint_id: number;
    score: number;
    reasons: string[];
  }[];
}

export interface LayoutDirection extends LayoutBlueprintInput {
  id: number;
  requirement_id: number;
  generation_version: number;
  strategy_level: "conservative" | "balanced" | "exploratory";
  name: string;
  rationale: string;
  applicable_reason: string;
  source_pattern_ids: number[];
  source_case_ids: number[];
  generation_mode: "model" | "heuristic";
  failure_reason: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LayoutDirectionSet {
  requirement: BusinessRequirement;
  generation_version: number;
  directions: LayoutDirection[];
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`请求失败 ${res.status}`);
  return res.json();
}

export const api = {
  analyze: (
    file: File,
    meta?: {
      uploader?: string;
      source_type?: string;
      source_url?: string;
      rights_note?: string;
      product_category?: string;
      asset_category?: string;
      asset_subcategory?: string;
    }
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(meta || {}).forEach(([key, value]) => {
      if (value) fd.append(key, value);
    });
    return fetch("/api/analyze", { method: "POST", body: fd }).then((r) =>
      j<CaseOut>(r)
    );
  },
  analyzeBatch: (
    files: File[],
    meta?: {
      uploader?: string;
      source_type?: string;
      source_url?: string;
      rights_note?: string;
      product_category?: string;
      asset_category?: string;
      asset_subcategory?: string;
    }
  ) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    Object.entries(meta || {}).forEach(([key, value]) => {
      if (value) fd.append(key, value);
    });
    return fetch("/api/analyze/batch", { method: "POST", body: fd }).then((r) =>
      j<{ batch_id: string; total: number }>(r)
    );
  },
  batchStatus: (id: string) =>
    fetch(`/api/analyze/batch/${id}`, { cache: "no-store" }).then((r) =>
      j<{
        batch_id: string;
        total: number;
        done: number;
        failed: number;
        skipped: number;
        status: string;
        case_ids: number[];
        errors: string[];
        skipped_files: string[];
        concurrency: number;
      }>(r)
    ),
  cases: (
    q = "",
    tag = "",
    assetCategory = "",
    assetSubcategory = "",
    projectId?: number,
    trustStatus = "",
    analysisMode = ""
  ) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (tag) p.set("tag", tag);
    if (assetCategory) p.set("asset_category", assetCategory);
    if (assetSubcategory) p.set("asset_subcategory", assetSubcategory);
    if (projectId) p.set("project_id", String(projectId));
    if (trustStatus) p.set("trust_status", trustStatus);
    if (analysisMode) p.set("analysis_mode", analysisMode);
    return fetch(`/api/cases?${p.toString()}`, { cache: "no-store" }).then((r) =>
      j<CaseOut[]>(r)
    );
  },
  case: (id: number | string) =>
    fetch(`/api/cases/${id}`, { cache: "no-store" }).then((r) => j<CaseOut>(r)),
  layoutBlueprints: (caseId: number | string) =>
    fetch(`/api/cases/${caseId}/layout-blueprints`, {
      cache: "no-store",
    }).then((r) => j<LayoutBlueprint[]>(r)),
  generateLayoutBlueprint: (caseId: number | string) =>
    fetch(`/api/cases/${caseId}/layout-blueprints/generate`, {
      method: "POST",
    }).then((r) => j<LayoutBlueprint>(r)),
  reviseLayoutBlueprint: (
    blueprintId: number,
    payload: LayoutBlueprintInput
  ) =>
    fetch(`/api/layout-blueprints/${blueprintId}/revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => j<LayoutBlueprint>(r)),
  verifyLayoutBlueprint: (blueprintId: number, editor: string) =>
    fetch(`/api/layout-blueprints/${blueprintId}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ editor }),
    }).then((r) => j<LayoutBlueprint>(r)),
  layoutPatterns: (filters?: {
    orientation?: string;
    scene?: string;
    channel?: string;
    review_status?: string;
  }) => {
    const params = new URLSearchParams();
    Object.entries(filters || {}).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return fetch(`/api/layout-patterns?${params.toString()}`, {
      cache: "no-store",
    }).then((r) => j<LayoutPattern[]>(r));
  },
  createLayoutPattern: (payload: LayoutPatternCreate) =>
    fetch("/api/layout-patterns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => j<LayoutPattern>(r)),
  verifyLayoutPattern: (patternId: number, editor: string) =>
    fetch(`/api/layout-patterns/${patternId}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ editor }),
    }).then((r) => j<LayoutPattern>(r)),
  createBusinessRequirement: (payload: BusinessRequirementCreate) =>
    fetch("/api/business-requirements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => j<BusinessRequirement>(r)),
  matchBusinessRequirement: (requirementId: number) =>
    fetch(`/api/business-requirements/${requirementId}/match`, {
      method: "POST",
    }).then((r) => j<BusinessRequirementMatch>(r)),
  generateLayoutDirections: (requirementId: number) =>
    fetch(`/api/business-requirements/${requirementId}/directions/generate`, {
      method: "POST",
    }).then((r) => j<LayoutDirectionSet>(r)),
  reviewCase: (id: number | string, review: CaseReviewInput) =>
    fetch(`/api/cases/${id}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(review),
    }).then((r) => j<CaseOut>(r)),
  caseVersions: (id: number | string) =>
    fetch(`/api/cases/${id}/versions`, { cache: "no-store" }).then((r) =>
      j<CaseVersion[]>(r)
    ),
  projects: () =>
    fetch("/api/projects", { cache: "no-store" }).then((r) =>
      j<ProjectOut[]>(r)
    ),
  assignCaseProject: (id: number | string, projectId: number | null) =>
    fetch(`/api/cases/${id}/project`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    }).then((r) => j<CaseOut>(r)),
  addPreference: (
    id: number | string,
    event_type: PreferenceEventType,
    actor = "",
    context = ""
  ) =>
    fetch(`/api/cases/${id}/preferences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type, value: 1, actor, context }),
    }).then((r) => j<{ id: number }>(r)),
  casePreferences: (id: number | string) =>
    fetch(`/api/cases/${id}/preferences`, { cache: "no-store" }).then((r) =>
      j<Record<string, number>>(r)
    ),
  trainingOverview: () =>
    fetch("/api/training/overview", { cache: "no-store" }).then((r) =>
      j<TrainingOverview>(r)
    ),
  trainingTaskPack: () =>
    fetch("/api/training/task-pack", { cache: "no-store" }).then((r) =>
      j<TrainingTaskPack>(r)
    ),
  trainingReadiness: () =>
    fetch("/api/training/readiness", { cache: "no-store" }).then((r) =>
      j<TrainingReadiness[]>(r)
    ),
  trainingReviewQuality: (projectId?: number) => {
    const params = new URLSearchParams();
    if (projectId) params.set("project_id", String(projectId));
    return fetch(`/api/training/review-quality?${params.toString()}`, {
      cache: "no-store",
    }).then((r) => j<ReviewQuality[]>(r));
  },
  batchReview: (
    caseIds: number[],
    action: "confirm" | "recommend" | "reject",
    reviewer: string,
    reviewNotes = "",
    businessLine = "",
    keepReasons: string[] = [],
    avoidReasons: string[] = []
  ) =>
    fetch("/api/training/batch-review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_ids: caseIds,
        action,
        reviewer,
        review_notes: reviewNotes,
        business_line: businessLine,
        keep_reasons: keepReasons,
        avoid_reasons: avoidReasons,
      }),
    }).then((r) =>
      j<{
        action: string;
        updated: number[];
        updated_count: number;
        missing: number[];
        failed: { case_id: number; detail: string }[];
      }>(r)
    ),
  batchCategorize: (
    caseIds: number[],
    assetCategory: "layout" | "style" | "color" | "photo",
    actor: string
  ) =>
    fetch("/api/training/batch-categorize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_ids: caseIds,
        asset_category: assetCategory,
        actor,
      }),
    }).then((r) =>
      j<{
        asset_category: string;
        updated: number[];
        updated_count: number;
      }>(r)
    ),
  categorySuggestions: (projectId?: number) => {
    const params = new URLSearchParams();
    if (projectId) params.set("project_id", String(projectId));
    return fetch(`/api/training/category-suggestions?${params.toString()}`, {
      cache: "no-store",
    }).then((r) => j<CategorySuggestion[]>(r));
  },
  categoryDiscovery: () =>
    fetch("/api/training/category-discovery", {
      cache: "no-store",
    }).then((r) => j<CategoryDiscovery[]>(r)),
  suggestCategories: (caseIds: number[]) =>
    fetch("/api/training/batch-suggest-categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_ids: caseIds }),
    }).then((r) =>
      j<{
        suggestions: CategorySuggestion[];
        suggested_count: number;
        failed: { case_id: number; detail: string }[];
      }>(r)
    ),
  startCategorySuggestionJob: (caseIds: number[]) =>
    fetch("/api/training/category-suggestion-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_ids: caseIds }),
    }).then((r) => j<CategorySuggestionJob>(r)),
  categorySuggestionJob: (jobId: number) =>
    fetch(`/api/training/category-suggestion-jobs/${jobId}`, {
      cache: "no-store",
    }).then((r) => j<CategorySuggestionJob>(r)),
  latestCategorySuggestionJob: () =>
    fetch("/api/training/category-suggestion-job-status", {
      cache: "no-store",
    }).then((r) => j<CategorySuggestionJob | null>(r)),
  reanalyzeCase: (id: number | string) =>
    fetch(`/api/cases/${id}/reanalyze`, { method: "POST" }).then((r) =>
      j<CaseOut>(r)
    ),
  serviceFeedback: (
    runId: number,
    outcome: "adopted" | "rejected" | "needs_revision",
    actor: string,
    notes = ""
  ) =>
    fetch(`/api/service-runs/${runId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome, actor, notes }),
    }).then((r) =>
      j<{
        run_id: number;
        previous_status: string;
        status: string;
        evidence_cases_updated: number[];
      }>(r)
    ),
  serviceRuns: (limit = 50) =>
    fetch(`/api/service-runs?limit=${limit}`, { cache: "no-store" }).then((r) =>
      j<ServiceRunSummary[]>(r)
    ),
  serviceRun: (id: number | string) =>
    fetch(`/api/service-runs/${id}`, { cache: "no-store" }).then((r) =>
      j<ServiceRunDetail>(r)
    ),
  tags: () =>
    fetch(`/api/tags`, { cache: "no-store" }).then((r) =>
      j<{ id: number; name: string; category: string; count: number }[]>(r)
    ),
  search: (input: SearchInput) => {
    const fd = new FormData();
    if (input.query_text) fd.append("query_text", input.query_text);
    if (input.product) fd.append("product", input.product);
    if (input.scene) fd.append("scene", input.scene);
    if (input.content_type) fd.append("content_type", input.content_type);
    if (input.source_type) fd.append("source_type", input.source_type);
    if (input.tags?.length) fd.append("tags", input.tags.join(","));
    if (input.reference_image) fd.append("reference_image", input.reference_image);
    return fetch("/api/search", { method: "POST", body: fd }).then((r) =>
      j<SearchHit[]>(r)
    );
  },
  concept: (businessLine = "") => {
    const params = new URLSearchParams();
    if (businessLine) params.set("business_line", businessLine);
    return fetch(`/api/concept?${params.toString()}`, { cache: "no-store" }).then(
      (r) => j<ConceptData>(r)
    );
  },
  methodology: () =>
    fetch(`/api/concept/methodology`, { method: "POST" }).then((r) =>
      j<{ enabled: boolean; methodology: string; model?: string; note?: string }>(r)
    ),
  recommend: (input: {
    text: string;
    industry?: string;
    channel?: string;
    campaign_stage?: string;
    focus_category?: "layout" | "style" | "color" | "photo";
    business_goal?: string;
    file?: File | null;
  }) => {
    const fd = new FormData();
    fd.append("text", input.text);
    fd.append("industry", input.industry || "");
    fd.append("channel", input.channel || "");
    fd.append("campaign_stage", input.campaign_stage || "");
    fd.append("focus_category", input.focus_category || "layout");
    fd.append("business_goal", input.business_goal || "");
    if (input.file) fd.append("file", input.file);
    return fetch(`/api/recommend`, { method: "POST", body: fd }).then((r) =>
      j<RecommendResult>(r)
    );
  },
};

export interface CaseReviewInput {
  reviewer: string;
  trust_status: "ai_unverified" | "verified" | "company_recommended" | "rejected";
  review_decision: "" | "adopt" | "adapt" | "reject";
  review_notes: string;
  business_line: string;
  channel: string;
  campaign_stage: string;
  business_goal: string;
  asset_category?: "layout" | "style" | "color" | "photo";
  name?: string;
  summary?: string;
  layout_type?: string;
  alignment?: string;
  hierarchy?: string[];
  style_tags?: string[];
  mood_keywords?: string[];
  color_description?: string;
  why_good?: string[];
  reusable_methods?: string[];
  prompt?: string;
  keep_reasons: string[];
  avoid_reasons: string[];
}

export interface CaseVersion {
  version: number;
  source: string;
  model_name: string;
  prompt_version: string;
  editor: string;
  created_at: string;
}

export interface ProjectOut {
  id: number;
  name: string;
  description: string;
  business_line: string;
  status: string;
  is_gold: boolean;
  case_count: number;
  verified_count: number;
  recommended_count: number;
  model_analyzed_count: number;
  company_published_count: number;
  created_at: string;
}

export type PreferenceEventType =
  | "like"
  | "dislike"
  | "adopt"
  | "reject"
  | "favorite"
  | "selected"
  | "published";

export interface TrainingOverview {
  total_cases: number;
  reviewed_cases: number;
  unreviewed_cases: number;
  verified_cases: number;
  recommended_cases: number;
  rejected_cases: number;
  preference_events: number;
  service_runs: number;
  adopted_service_runs: number;
  service_outcomes: Record<string, number>;
  business_line_coverage: Record<
    string,
    {
      total: number;
      model_analyzed: number;
      company_published: number;
      trusted: number;
      recommended: number;
    }
  >;
  training_matrix: {
    business_line: string;
    project_id: number | null;
    ready_categories: number;
    cells: Record<
      "layout" | "style" | "color" | "photo",
      {
        total: number;
        company_published: number;
        model_analyzed: number;
        trusted: number;
        recommended: number;
        ready: boolean;
        gaps: string[];
      }
    >;
  }[];
  maturity_score: number;
  targets: {
    trusted_cases: number;
    recommended_cases: number;
    preference_events: number;
  };
  category_coverage: Record<
    string,
    { total: number; trusted: number; recommended: number }
  >;
}

export interface TrainingReadiness {
  business_line: string;
  stage:
    | "collect"
    | "organize"
    | "analyze"
    | "verify"
    | "curate"
    | "operate"
    | "feedback"
    | "operational";
  score: number;
  next_action: string;
  service_mode: "reference_only" | "pilot" | "operational";
  review_candidate_ids: number[];
  weekly_actions: string[];
  owner_role: string;
  acceptance_criteria: string[];
  asset_category_coverage: Record<
    "layout" | "style" | "color" | "photo",
    { current: number; target: number; met: boolean }
  >;
  coverage_gaps: ("layout" | "style" | "color" | "photo")[];
  gates: Record<
    | "company_assets"
    | "category_balance"
    | "model_analyzed"
    | "human_verified"
    | "company_recommended"
    | "service_runs"
    | "adopted_runs",
    { current: number; target: number; met: boolean }
  >;
}

export interface TrainingTaskPack {
  generated_at: string;
  total_tasks: number;
  ready_cells: number;
  total_cells: number;
  tasks: {
    task_id: string;
    business_line: string;
    project_id: number | null;
    asset_category: "layout" | "style" | "color" | "photo";
    category_label: string;
    priority: "urgent" | "high" | "normal";
    owner_role: string;
    next_action: string;
    candidate_case_ids: number[];
    current: {
      company_published: number;
      model_analyzed: number;
      trusted: number;
      recommended: number;
    };
    acceptance_criteria: string[];
  }[];
}

export interface ReviewQuality {
  case_id: number;
  score: number;
  ready: boolean;
  warnings: string[];
  model_name: string;
  analysis_version: number;
}

export interface CategorySuggestion {
  id: number;
  case_id: number;
  suggested_category: "layout" | "style" | "color" | "photo";
  confidence: number;
  reason: string;
  signals: string[];
  model_name: string;
  status: "pending" | "accepted" | "overridden" | "superseded";
  reviewer: string;
  created_at: string;
}

export interface CategorySuggestionJob {
  id: number;
  status:
    | "queued"
    | "running"
    | "completed"
    | "completed_with_errors"
    | "failed"
    | "interrupted";
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  errors: { case_id: number | null; detail: string }[];
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface CategoryDiscovery {
  business_line: string;
  coverage: Record<"layout" | "style" | "color" | "photo", number>;
  gaps: {
    category: "layout" | "style" | "color" | "photo";
    label: string;
    needed: number;
    candidate_count: number;
  }[];
  candidates: Record<
    "layout" | "style" | "color" | "photo",
    {
      case_id: number;
      case_name: string;
      image_url: string;
      current_category: string;
      suggested_category: "layout" | "style" | "color" | "photo";
      confidence: number;
      reason: string;
      signals: string[];
      status: string;
    }[]
  >;
  suggested_count: number;
  total_assets: number;
}

export interface SearchInput {
  query_text?: string;
  product?: string;
  scene?: string;
  content_type?: string;
  source_type?: string;
  tags?: string[];
  reference_image?: File | null;
}

export interface SearchHit {
  case: CaseOut;
  score: number;
  reasons: string[];
}

export interface DistItem {
  name: string;
  count: number;
  pct: number;
}

export interface ConceptData {
  scope: string;
  total: number;
  contributing_cases: number;
  weighted_total: number;
  enough: boolean;
  threshold: number;
  trusted_count: number;
  company_published_count: number;
  model_analyzed_count: number;
  evidence_count: number;
  service_run_count: number;
  adopted_run_count: number;
  trust_counts: Record<string, number>;
  category_weights: Record<string, number>;
  distributions: Record<string, DistItem[]>;
  visual_dna: {
    colors: { hex: string; count: number }[];
    top_layout: string;
    top_style: string;
    top_grid: string;
  };
  principles: string[];
  explicit_guidance: {
    keep: { text: string; count: number }[];
    avoid: { text: string; count: number }[];
  };
  by_industry: {
    industry: string;
    count: number;
    top_layouts: DistItem[];
    top_styles: string[];
    top_colors: string[];
    principle: string;
  }[];
  weight_rules: {
    trust: Record<string, number>;
    preference: Record<string, number>;
    gold_project_multiplier: number;
  };
}

export interface RecommendResult {
  run_id: number;
  directions: string[];
  recommended_tags: string[];
  reference_case_ids: number[];
  prompt: string;
  has_reference: boolean;
  reference_style: string[];
  reference_palette: string[];
  reference_layout: string;
  reference_font: string;
  reference_summary: string;
  preference_applied: boolean;
  company_evidence: {
    scope: string;
    applied: boolean;
    evidence_level: "insufficient" | "growing" | "strong";
    trusted_cases: number;
    company_published_cases: number;
    model_analyzed_cases: number;
    evidence_cases: number;
    service_runs: number;
    adopted_runs: number;
    usage_mode: "reference_only" | "pilot" | "operational";
    layouts: string[];
    styles: string[];
    grids: string[];
    fonts: string[];
    color_families: string[];
    keep_rules: string[];
    avoid_rules: string[];
    industry_profile?: Record<string, unknown> | null;
  };
  company_maturity: "insufficient" | "growing" | "strong";
  company_usage_mode: "reference_only" | "pilot" | "operational";
  focus_category: "layout" | "style" | "color" | "photo";
  evidence_case_ids: number[];
}

export interface ServiceRunSummary {
  id: number;
  request_text: string;
  industry: string;
  channel: string;
  campaign_stage: string;
  focus_category: "layout" | "style" | "color" | "photo";
  business_goal: string;
  status: "generated" | "adopted" | "rejected" | "needs_revision";
  actor: string;
  feedback: string;
  evidence_case_ids: number[];
  created_at: string;
  updated_at: string;
}

export interface ServiceRunDetail extends ServiceRunSummary {
  company_profile_snapshot: RecommendResult["company_evidence"];
  result: RecommendResult;
}
