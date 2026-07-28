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
  name: string;
  content_type: string;
  product_category: string;
  asset_category: string;
  asset_subcategory: string;
  industry: string;
  scene: string;
  summary: string;
  trust_status: string;
  status: string;
  created_at: string;
  image: ImageOut | null;
  tags: TagOut[];
  analysis: AnalysisData | null;
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
  cases: (q = "", tag = "", assetCategory = "", assetSubcategory = "") => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (tag) p.set("tag", tag);
    if (assetCategory) p.set("asset_category", assetCategory);
    if (assetSubcategory) p.set("asset_subcategory", assetSubcategory);
    return fetch(`/api/cases?${p.toString()}`, { cache: "no-store" }).then((r) =>
      j<CaseOut[]>(r)
    );
  },
  case: (id: number | string) =>
    fetch(`/api/cases/${id}`, { cache: "no-store" }).then((r) => j<CaseOut>(r)),
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
  concept: () =>
    fetch(`/api/concept`, { cache: "no-store" }).then((r) => j<ConceptData>(r)),
  methodology: () =>
    fetch(`/api/concept/methodology`, { method: "POST" }).then((r) =>
      j<{ enabled: boolean; methodology: string; model?: string; note?: string }>(r)
    ),
  recommend: (text: string, industry = "", file?: File | null) => {
    const fd = new FormData();
    fd.append("text", text);
    fd.append("industry", industry);
    if (file) fd.append("file", file);
    return fetch(`/api/recommend`, { method: "POST", body: fd }).then((r) =>
      j<RecommendResult>(r)
    );
  },
};

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
  total: number;
  enough: boolean;
  threshold: number;
  distributions: Record<string, DistItem[]>;
  visual_dna: {
    colors: { hex: string; count: number }[];
    top_layout: string;
    top_style: string;
    top_grid: string;
  };
  principles: string[];
  by_industry: {
    industry: string;
    count: number;
    top_layouts: DistItem[];
    top_styles: string[];
    top_colors: string[];
    principle: string;
  }[];
}

export interface RecommendResult {
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
}
