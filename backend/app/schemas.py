"""Pydantic 数据结构，对应技术方案「六、AI输出结构」。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel


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
    trust_status: str = "ai_unverified"
    status: str = "public"
    created_at: dt.datetime
    image: ImageOut | None = None
    tags: list[TagOut] = []
    analysis: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class CaseReviewInput(BaseModel):
    reviewer: str
    trust_status: Literal[
        "ai_unverified", "verified", "company_recommended", "rejected"
    ] = "verified"
    review_decision: Literal["", "adopt", "adapt", "reject"] = ""
    review_notes: str = ""
    business_line: str = ""
    channel: str = ""
    campaign_stage: str = ""
    business_goal: str = ""
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


class SearchHit(BaseModel):
    """文本、筛选条件与参考图混合检索结果。"""

    case: CaseOut
    score: float
    reasons: list[str] = []
