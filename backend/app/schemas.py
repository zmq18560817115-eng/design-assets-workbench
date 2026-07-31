"""Pydantic 数据结构，对应技术方案「六、AI输出结构」。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------- AI 输出结构 ----------
class ColorSystem(BaseModel):
    palette: list[str] = []          # 主要色值
    primary: str = ""                # 主色
    description: str = ""            # 色彩体系描述


class Composition(BaseModel):
    type: str = ""                   # 构图方式（居中/对称/三分/留白...）
    description: str = ""


class Light(BaseModel):
    type: str = ""                   # 光影语言
    description: str = ""


class Layout(BaseModel):
    """排版拆解（含可量化的硬版式参数）。"""

    layout_type: str = ""            # 版式类型（满版/中轴/分栏/网格/留白...）
    alignment: str = ""              # 对齐方式
    hierarchy: list[str] = []        # 信息层级（主标题>副标题>正文...）
    whitespace: str = ""             # 留白策略
    focal: str = ""                  # 视觉重心 / 阅读引导路径
    # —— 硬版式参数 ——
    grid_columns: str = ""           # 栅格列数（单列/双栏/三栏/多栏网格）
    modules: str = ""                # 模块划分（纵向内容分块数）
    margins: str = ""                # 页边距（四周留白比例）
    spacing: str = ""                # 模块间距 / 疏密
    content_ratio: str = ""          # 内容区占比
    grid_metrics: dict[str, float] = {}  # 原始度量（占比等），供进一步生成使用
    description: str = ""
    canvas_ratio: str = ""
    orientation: str = ""
    reading_flow: str = ""
    focal_region: dict[str, float] = {}
    information_density: str = ""
    text_image_ratio: float | None = None
    blueprint_modules: list[dict[str, Any]] = []
    layout_summary: str = ""


class Typography(BaseModel):
    """文字 / 标题 / 字体拆解。"""

    title_treatment: str = ""        # 标题处理方式
    font_tone: str = ""              # 字体调性建议（无衬线/衬线/手写...）
    size_contrast: str = ""          # 字号层级对比
    pairing: str = ""                # 中英文 / 主辅字体搭配
    text_ratio: str = ""             # 文字占比（重文字/图文均衡/以图为主）
    description: str = ""


class VisualStyle(BaseModel):
    style_tags: list[str] = []       # 风格标签
    mood_keywords: list[str] = []    # 情绪关键词
    brand_position: str = ""         # 品牌定位


class DesignRules(BaseModel):
    why_good: list[str] = []         # 为什么优秀
    reusable_methods: list[str] = []  # 可复用方法


class DeepInsights(BaseModel):
    """视觉大模型的深度语义解析（配置真实 VLM 时才有）。"""

    target_audience: str = ""              # 目标受众
    applicable_scenes: list[str] = []      # 适用场景
    color_roles: list[str] = []            # 色彩角色（主/辅/点缀及其作用）
    composition_principles: list[str] = [] # 构图原理
    emotion_narrative: str = ""            # 情绪 / 叙事
    critique: list[str] = []               # 专业点评
    improvement: list[str] = []            # 提升建议


class CaseBasics(BaseModel):
    image_type: str = ""             # 图片类型
    industry: str = ""               # 行业
    scene: str = ""                  # 使用场景


class AnalysisResult(BaseModel):
    """一次完整的 AI 拆解输出。"""

    basics: CaseBasics
    style: VisualStyle
    color: ColorSystem
    composition: Composition
    light: Light
    material: str = ""               # 材质表现
    layout: Layout                   # 排版
    typography: Typography           # 文字 / 标题 / 字体
    design_rules: DesignRules
    prompt: str = ""                 # AI 绘图提示词
    summary: str = ""                # 一句话总结
    name: str = ""                   # 案例名称
    tags: list[str] = []             # 汇总标签
    insights: DeepInsights | None = None  # VLM 深度解析
    analyzed_by: str = "启发式规则"   # 语义来源：启发式规则 / 模型名


# ---------- API 出参 ----------
class ImageOut(BaseModel):
    id: int
    url: str
    filename: str
    source: str
    source_type: str = "external_reference"
    source_url: str = ""
    rights_note: str = ""
    visibility: str = "team"
    uploader: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class TagOut(BaseModel):
    id: int
    name: str
    category: str

    class Config:
        from_attributes = True


class CaseOut(BaseModel):
    id: int
    project_id: int | None = None
    name: str
    content_type: str = ""
    product_category: str = ""
    product_name: str = ""
    content_purpose: str = ""
    page_role: Literal[
        "cover_hook", "problem_statement", "cause_explanation",
        "product_display", "function_explanation", "parameter_comparison",
        "usage_step", "service_assurance", "conclusion", "call_to_action", "other",
    ] = "other"
    sequence_index: int | None = None
    brief_ref: str = ""
    metadata_status: Literal["manifest", "inferred", "manual"] = "inferred"
    asset_category: str = "layout"
    asset_subcategory: str = ""
    industry: str
    scene: str
    summary: str
    business_line: str = ""
    channel: str = ""
    campaign_stage: str = ""
    business_goal: str = ""
    review_decision: str = ""
    review_notes: str = ""
    reviewer: str = ""
    reviewed_at: dt.datetime | None = None
    blueprint_correct: bool = False
    business_reusable: bool = False
    trust_status: str = "ai_unverified"
    status: str = "public"
    created_at: dt.datetime
    image: ImageOut | None = None
    tags: list[TagOut] = []
    analysis: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class CaseBusinessUpdate(BaseModel):
    product_name: str = ""
    content_purpose: str = ""
    page_role: Literal[
        "cover_hook", "problem_statement", "cause_explanation",
        "product_display", "function_explanation", "parameter_comparison",
        "usage_step", "service_assurance", "conclusion", "call_to_action", "other",
    ] = "other"
    sequence_index: int | None = Field(default=None, ge=0)
    brief_ref: str = ""
    business_line: str = ""
    product_category: str = ""
    channel: str = ""
    campaign_stage: str = ""


class NormalizedRegion(BaseModel):
    """A rectangle in normalized 0..1 canvas coordinates."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stays_inside_canvas(self):
        if self.x + self.width > 1 + 1e-9:
            raise ValueError("x + width must not exceed 1")
        if self.y + self.height > 1 + 1e-9:
            raise ValueError("y + height must not exceed 1")
        return self


class LayoutMargins(BaseModel):
    top: float = Field(default=0, ge=0, le=1)
    right: float = Field(default=0, ge=0, le=1)
    bottom: float = Field(default=0, ge=0, le=1)
    left: float = Field(default=0, ge=0, le=1)


class LayoutModule(NormalizedRegion):
    id: str = Field(min_length=1, max_length=80)
    type: Literal[
        "main_title", "subtitle", "body_text", "product_image", "person_image",
        "scene_image", "selling_point", "feature_list", "parameter_table",
        "price", "logo", "cta", "footnote", "decoration", "background", "other",
    ]
    label: str = ""
    importance: int = Field(default=1, ge=1)
    content_summary: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    # Legacy aliases remain in responses so existing clients keep working.
    priority: int = Field(default=1, ge=1)
    alignment: str = ""
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        type_aliases = {
            "title": "main_title",
            "supporting_text": "body_text",
        }
        value["type"] = type_aliases.get(value.get("type"), value.get("type", "other"))
        value.setdefault("label", value.get("description", ""))
        value.setdefault("content_summary", value.get("description", ""))
        value.setdefault("importance", value.get("priority", 1))
        value.setdefault("priority", value.get("importance", 1))
        value.setdefault("description", value.get("content_summary", ""))
        return value


class LayoutBlueprintInput(BaseModel):
    canvas_ratio: str = Field(default="1:1", min_length=3, max_length=24)
    orientation: Literal["portrait", "landscape", "square"]
    grid_columns: int = Field(default=1, ge=1, le=24)
    grid_rows: int = Field(default=1, ge=1, le=48)
    margins: LayoutMargins = Field(default_factory=LayoutMargins)
    alignment: str = ""
    reading_flow: str = ""
    focal_region: NormalizedRegion | None = None
    information_density: str = ""
    text_image_ratio: float = Field(default=0.5, ge=0, le=1)
    module_count: int | None = Field(default=None, ge=0)
    modules_json: list[LayoutModule] = Field(default_factory=list)
    layout_signature: str = ""
    review_status: Literal[
        "ai_generated", "corrected", "verified", "ai_unverified", "human_edited"
    ] = "ai_generated"
    model_name: str = ""
    prompt_version: str = "layout-blueprint-v1"
    editor: str = ""

    @model_validator(mode="after")
    def module_count_matches(self):
        from .layout_blueprint import (
            layout_signature,
            validate_canvas_ratio,
            validate_modules,
        )
        validate_canvas_ratio(self.canvas_ratio)
        raw_modules = [module.model_dump() for module in self.modules_json]
        validate_modules(raw_modules, self.module_count)
        self.module_count = len(raw_modules)
        self.layout_signature = layout_signature(
            {**self.model_dump(exclude={"layout_signature"}), "modules_json": raw_modules}
        )
        if self.review_status in {"ai_generated", "ai_unverified"} and not self.model_name.strip():
            raise ValueError("AI layout blueprints must record model_name")
        if self.review_status in {"corrected", "human_edited", "verified"} and not self.editor.strip():
            raise ValueError("human reviewed layout blueprints must record editor")
        return self


class LayoutBlueprintOut(LayoutBlueprintInput):
    id: int
    case_id: int
    module_count: int
    version: int
    created_at: dt.datetime
    updated_at: dt.datetime


class LayoutBlueprintVerifyInput(BaseModel):
    editor: str = Field(min_length=1, max_length=120)
    version: int | None = Field(default=None, ge=1)


class LayoutPatternCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    source_blueprint_ids: list[int] = Field(min_length=1)
    industry_tags: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    channel_tags: list[str] = Field(default_factory=list)
    business_goal_tags: list[str] = Field(default_factory=list)
    usage_notes: str = ""
    editor: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def unique_sources(self):
        self.source_blueprint_ids = list(dict.fromkeys(self.source_blueprint_ids))
        return self


class LayoutPatternUpdate(LayoutPatternCreate):
    review_status: Literal["human_edited", "verified"] = "human_edited"


class LayoutPatternOut(BaseModel):
    id: int
    name: str
    pattern_code: str = ""
    description: str
    canvas_ratio: str
    orientation: Literal["portrait", "landscape", "square"]
    grid_columns: int
    grid_rows: int
    margins: LayoutMargins
    alignment: str
    reading_flow: str
    layout_signature: str = ""
    focal_region: NormalizedRegion | None
    information_density: str
    text_image_ratio: float
    module_count: int
    modules_json: list[LayoutModule]
    module_structure_json: list[LayoutModule] = Field(default_factory=list)
    average_positions_json: list[LayoutModule] = Field(default_factory=list)
    required_modules_json: list[str] = Field(default_factory=list)
    optional_modules_json: list[str] = Field(default_factory=list)
    suitable_scenes_json: list[str] = Field(default_factory=list)
    unsuitable_scenes_json: list[str] = Field(default_factory=list)
    evidence_case_ids_json: list[int] = Field(default_factory=list)
    evidence_blueprint_ids_json: list[int] = Field(default_factory=list)
    evidence_count: int = 0
    confidence_level: Literal["candidate", "medium", "high"] = "candidate"
    discovery_method: str = ""
    generated_at: dt.datetime | None = None
    source_blueprint_ids: list[int]
    source_case_ids: list[int]
    industry_tags: list[str]
    scene_tags: list[str]
    channel_tags: list[str]
    business_goal_tags: list[str]
    product_category_tags_json: list[str] = Field(default_factory=list)
    content_purpose_tags_json: list[str] = Field(default_factory=list)
    campaign_stage_tags_json: list[str] = Field(default_factory=list)
    business_context_json: dict = Field(default_factory=dict)
    business_context_review_status: Literal["suggested", "verified", "stale"] = "suggested"
    business_context_reviewer: str = ""
    usage_notes: str
    version: int
    review_status: Literal["draft", "human_edited", "verified", "disabled"]
    reviewer: str = ""
    model_name: str
    prompt_version: str
    editor: str
    created_at: dt.datetime
    updated_at: dt.datetime


class LayoutPatternRebuildInput(BaseModel):
    dry_run: bool = True
    similarity_threshold: float = Field(default=0.72, ge=0.5, le=1.0)
    minimum_evidence: int = Field(default=3, ge=3, le=100)


class LayoutPatternPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    module_structure_json: list[LayoutModule] | None = None
    suitable_scenes_json: list[str] | None = None
    unsuitable_scenes_json: list[str] | None = None
    product_category_tags_json: list[str] | None = None
    content_purpose_tags_json: list[str] | None = None
    campaign_stage_tags_json: list[str] | None = None
    business_context_review_status: Literal["suggested", "verified", "stale"] | None = None
    reviewer: str = ""


class LayoutSearchGroundTruthCreate(BaseModel):
    requirement_id: int = Field(ge=1)
    result_type: Literal["pattern", "case"]
    result_id: int = Field(ge=1)
    expected_relevance: Literal["relevant", "partially_relevant", "irrelevant"]
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = ""
    dataset_version: str = Field(min_length=1, max_length=80)
    dataset_split: Literal["calibration", "holdout"]


class LayoutSearchGroundTruthFreeze(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)


class LayoutSearchGroundTruthUpdate(BaseModel):
    expected_relevance: Literal[
        "relevant", "partially_relevant", "irrelevant"
    ]
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1)
    dataset_split: Literal["calibration", "holdout"]


class LayoutSearchEvaluationRunInput(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)
    dataset_split: Literal["calibration", "holdout"] | None = None


class LayoutSearchDatasetCreate(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    dataset_kind: Literal["real", "fixture"] = "real"
    created_by: str = Field(min_length=1, max_length=120)


class AnalysisDatasetCreate(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    product_category: str = ""
    description: str = ""
    created_by: str = Field(min_length=1, max_length=120)


class AnalysisDatasetItemUpsert(BaseModel):
    case_id: int = Field(ge=1)
    dataset_split: Literal["calibration", "holdout"]
    reviewer: str = ""
    reason: str = ""


class AnalysisGroundTruthUpdate(BaseModel):
    has_product: bool
    product_regions: list[NormalizedRegion] = Field(default_factory=list)
    primary_text_regions: list[NormalizedRegion] = Field(default_factory=list)
    modules: list[LayoutModule] = Field(default_factory=list)
    containment: list[dict[str, str]] = Field(default_factory=list)
    allowed_overlaps: list[list[str]] = Field(default_factory=list)
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1)


class AnalysisRuntimeVersionCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=160)
    model_provider: str = Field(min_length=1, max_length=80)
    prompt_version: str = Field(min_length=1, max_length=80)
    prompt_text: str = ""
    validator_version: str = Field(min_length=1, max_length=80)
    validator_config: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(min_length=1, max_length=120)


class AnalysisEvaluationRunCreate(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)
    dataset_split: Literal["calibration", "holdout"]
    runtime_version_id: int = Field(ge=1)
    created_by: str = Field(min_length=1, max_length=120)
    confirm_consume_holdout: bool = False


class AnalysisVersionFreezeInput(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=80)
    runtime_version_id: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=120)


class AnalysisHoldoutUnsealInput(BaseModel):
    actor: str = Field(min_length=1, max_length=120)
    confirm_consumed: bool = False


class AnalysisResultRetryInput(BaseModel):
    actor: str = Field(min_length=1, max_length=120)


class BusinessRequirementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    request_text: str = ""
    industry: str = ""
    product_category: str = ""
    channel: str = ""
    canvas_ratio: str = ""
    orientation: Literal["", "portrait", "landscape", "square"] = ""
    campaign_stage: str = ""
    business_goal: str = ""
    target_audience: str = ""
    key_message: str = ""
    mandatory_elements: list[str] = Field(default_factory=list)
    content_purpose: str = ""
    required_modules_json: list[str] = Field(default_factory=list)
    optional_modules_json: list[str] = Field(default_factory=list)
    forbidden_modules_json: list[str] = Field(default_factory=list)
    selling_points_json: list[str] = Field(default_factory=list)
    style_keywords_json: list[str] = Field(default_factory=list)
    raw_requirement: str = ""
    reference_case_ids_json: list[int] = Field(default_factory=list)
    reference_image_path: str = ""
    creator: str = ""
    information_density: Literal["", "low", "medium", "high"] = ""
    reference_case_ids: list[int] = Field(default_factory=list)
    created_by: str = ""
    status: Literal["draft", "confirmed", "archived", "ready"] = "draft"

    @model_validator(mode="after")
    def validate_requirement(self):
        from .layout_blueprint import validate_canvas_ratio
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title 不能为空")
        if self.canvas_ratio:
            validate_canvas_ratio(self.canvas_ratio)
        conflict = sorted(
            set(self.required_modules_json) & set(self.forbidden_modules_json)
        )
        if conflict:
            raise ValueError(f"必需模块与禁止模块冲突: {conflict}")
        self.reference_case_ids_json = list(
            dict.fromkeys(self.reference_case_ids_json or self.reference_case_ids)
        )
        self.reference_case_ids = list(self.reference_case_ids_json)
        self.raw_requirement = self.raw_requirement or self.request_text
        self.request_text = self.request_text or self.raw_requirement
        self.creator = self.creator or self.created_by
        self.created_by = self.created_by or self.creator
        return self


class BusinessRequirementUpdate(BusinessRequirementCreate):
    pass


class BusinessRequirementOut(BusinessRequirementCreate):
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime


class LayoutSearchInput(BaseModel):
    pattern_limit: int = Field(default=10, ge=1, le=50)
    case_limit: int = Field(default=20, ge=1, le=100)
    include_unverified: bool = False
    reanalyze_reference: bool = False


class LayoutSearchFeedbackCreate(BaseModel):
    result_type: Literal["pattern", "case"]
    result_id: int = Field(ge=1)
    rank: int = Field(ge=1)
    relevance: Literal["relevant", "partially_relevant", "irrelevant"]
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str = ""


class LayoutPatternMatchOut(BaseModel):
    pattern: LayoutPatternOut
    score: float
    reasons: list[str]


class CaseLayoutMatchOut(BaseModel):
    case_id: int
    name: str
    blueprint_id: int
    score: float
    reasons: list[str]


class BusinessRequirementMatchOut(BaseModel):
    requirement: BusinessRequirementOut
    pattern_matches: list[LayoutPatternMatchOut]
    case_matches: list[CaseLayoutMatchOut]


class LayoutDirectionOut(BaseModel):
    id: int
    requirement_id: int
    generation_version: int
    strategy_level: Literal["conservative", "balanced", "exploratory"]
    name: str
    rationale: str
    applicable_reason: str
    canvas_ratio: str
    orientation: Literal["portrait", "landscape", "square"]
    grid_columns: int
    grid_rows: int
    margins: LayoutMargins
    alignment: str
    reading_flow: str
    focal_region: NormalizedRegion | None
    information_density: str
    text_image_ratio: float
    module_count: int
    modules_json: list[LayoutModule]
    source_pattern_ids: list[int]
    source_case_ids: list[int]
    model_name: str
    prompt_version: str
    generation_mode: Literal["model", "heuristic"]
    failure_reason: str
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class LayoutDirectionSetOut(BaseModel):
    requirement: BusinessRequirementOut
    generation_version: int
    directions: list[LayoutDirectionOut]

    @model_validator(mode="after")
    def exactly_three_directions(self):
        if len(self.directions) != 3:
            raise ValueError("direction set must contain exactly three directions")
        return self


class LayoutDirectionFeedbackCreate(BaseModel):
    action: Literal[
        "selected",
        "adjustment_requested",
        "adjusted_confirmed",
        "rejected",
    ]
    actor: str = Field(min_length=1, max_length=120)
    notes: str = ""
    adjusted_modules_json: list[LayoutModule] | None = None

    @model_validator(mode="after")
    def adjusted_snapshot_required(self):
        if self.action == "adjusted_confirmed" and not self.adjusted_modules_json:
            raise ValueError(
                "adjusted_confirmed requires adjusted_modules_json"
            )
        if self.adjusted_modules_json:
            module_ids = [item.id for item in self.adjusted_modules_json]
            if len(module_ids) != len(set(module_ids)):
                raise ValueError("adjusted layout module ids must be unique")
        return self


class LayoutDirectionFeedbackOut(LayoutDirectionFeedbackCreate):
    id: int
    requirement_id: int
    direction_id: int
    created_at: dt.datetime


class CaseReviewInput(BaseModel):
    reviewer: str
    trust_status: Literal[
        "ai_unverified", "verified", "company_recommended", "rejected"
    ] = "verified"
    review_decision: Literal["", "adopt", "adapt", "reject"] = ""
    review_notes: str = ""
    blueprint_correct: bool | None = None
    business_reusable: bool | None = None
    business_line: str | None = None
    channel: str | None = None
    campaign_stage: str | None = None
    business_goal: str | None = None
    product_name: str | None = None
    content_purpose: str | None = None
    page_role: Literal[
        "cover_hook", "problem_statement", "cause_explanation",
        "product_display", "function_explanation", "parameter_comparison",
        "usage_step", "service_assurance", "conclusion", "call_to_action", "other",
    ] | None = None
    sequence_index: int | None = Field(default=None, ge=0)
    brief_ref: str | None = None
    asset_category: Literal["layout", "style", "color", "photo"] | None = None
    name: str | None = None
    summary: str | None = None
    layout_type: str | None = None
    alignment: str | None = None
    hierarchy: list[str] | None = None
    style_tags: list[str] | None = None
    mood_keywords: list[str] | None = None
    color_description: str | None = None
    why_good: list[str] | None = None
    reusable_methods: list[str] | None = None
    prompt: str | None = None
    keep_reasons: list[str] = Field(default_factory=list)
    avoid_reasons: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    business_line: str = ""
    status: Literal["active", "archived"] = "active"
    is_gold: bool = False


class ProjectOut(ProjectCreate):
    id: int
    case_count: int = 0
    verified_count: int = 0
    recommended_count: int = 0
    model_analyzed_count: int = 0
    company_published_count: int = 0
    created_at: dt.datetime


class CaseProjectInput(BaseModel):
    project_id: int | None = None


class PreferenceEventInput(BaseModel):
    event_type: Literal[
        "like", "dislike", "adopt", "reject", "favorite", "selected", "published"
    ]
    value: int = 1
    actor: str = ""
    context: str = ""


class BatchReviewInput(BaseModel):
    case_ids: list[int]
    action: Literal["confirm", "recommend", "reject"]
    reviewer: str
    review_notes: str = ""
    business_line: str = ""
    keep_reasons: list[str] = Field(default_factory=list)
    avoid_reasons: list[str] = Field(default_factory=list)


class BatchCategorizeInput(BaseModel):
    case_ids: list[int]
    asset_category: Literal["layout", "style", "color", "photo"]
    actor: str


class BatchCategorySuggestionInput(BaseModel):
    case_ids: list[int]


class RequirementInput(BaseModel):
    """需求生成页入参。"""

    text: str
    industry: str = ""


class VisualDirection(BaseModel):
    """需求 → 视觉方向 推荐结果。"""

    directions: list[str]
    recommended_tags: list[str]
    reference_case_ids: list[int]
    prompt: str
    # —— 若上传了意向图，返回对参考图的视觉解析 ——
    has_reference: bool = False
    reference_style: list[str] = []       # 参考图风格标签
    reference_palette: list[str] = []     # 参考图主色板
    reference_layout: str = ""            # 参考图版式
    reference_font: str = ""              # 参考图字体调性
    reference_summary: str = ""           # 参考图一句话解析


    preference_applied: bool = False
    company_evidence: dict[str, Any] = {}
    company_maturity: str = "insufficient"
    company_usage_mode: str = "reference_only"
    focus_category: Literal["layout", "style", "color", "photo"] = "layout"
    evidence_case_ids: list[int] = []
    run_id: int = 0


class ServiceFeedbackInput(BaseModel):
    outcome: Literal["adopted", "rejected", "needs_revision"]
    actor: str
    notes: str = ""


class SearchHit(BaseModel):
    """文本、筛选条件与参考图混合检索结果。"""

    case: CaseOut
    score: float
    reasons: list[str] = []
