"""第一阶段数据库模型。

核心闭环：素材进入 → AI 拆解 → 多模态检索 → 案例选择。
保留旧仓库的 images / cases / analysis / tags 关系，补齐来源治理、可信状态、
模型版本和分析版本记录，便于后续迁移到 PostgreSQL。
"""
import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base

# 案例与标签的多对多关联表
case_tags = Table(
    "case_tags",
    Base.metadata,
    Column("case_id", ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Image(Base):
    """图片表：记录上传的原始素材。"""

    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)          # 可访问的图片地址
    filename = Column(String, nullable=False)
    source = Column(String, default="upload")     # 进入方式：upload / batch
    source_type = Column(String, default="external_reference", index=True)
    source_url = Column(String, default="")
    rights_note = Column(Text, default="")
    visibility = Column(String, default="team")
    uploader = Column(String, default="anonymous")  # 上传人
    phash = Column(String, default="", index=True)  # 感知哈希（去重）
    original_sha256 = Column(String, default="", index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case", back_populates="image", uselist=False)


class Case(Base):
    """案例表：一张图片拆解后形成的「案例资产卡」。"""

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"))
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String, nullable=False)
    content_type = Column(String, default="", index=True)
    product_category = Column(String, default="", index=True)
    product_name = Column(String, default="", index=True)
    content_purpose = Column(String, default="", index=True)
    page_role = Column(String, default="other", index=True)
    sequence_index = Column(Integer, nullable=True, index=True)
    brief_ref = Column(String, default="", index=True)
    metadata_status = Column(String, default="inferred", index=True)
    asset_category = Column(String, default="layout", index=True)
    asset_subcategory = Column(String, default="", index=True)
    industry = Column(String, default="")        # 行业
    scene = Column(String, default="")           # 使用场景
    summary = Column(Text, default="")           # 一句话总结
    business_line = Column(String, default="", index=True)
    channel = Column(String, default="", index=True)
    campaign_stage = Column(String, default="", index=True)
    business_goal = Column(Text, default="")
    review_decision = Column(String, default="", index=True)
    review_notes = Column(Text, default="")
    reviewer = Column(String, default="")
    reviewed_at = Column(DateTime, nullable=True)
    blueprint_correct = Column(Boolean, default=False, index=True)
    business_reusable = Column(Boolean, default=False, index=True)
    trust_status = Column(String, default="ai_unverified", index=True)
    status = Column(String, default="public", index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    image = relationship("Image", back_populates="case")
    project = relationship("Project", back_populates="cases")
    analysis = relationship(
        "Analysis", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    tags = relationship("Tag", secondary=case_tags, back_populates="cases")
    layout_blueprints = relationship(
        "LayoutBlueprint",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="LayoutBlueprint.version",
    )


class Analysis(Base):
    """分析结果表：AI Agent 流水线输出的结构化拆解结果。"""

    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"))
    # 以 JSON 文本存储，兼顾 SQLite 与 PostgreSQL
    color = Column(Text, default="{}")       # 色彩体系
    composition = Column(Text, default="{}") # 构图方式
    light = Column(Text, default="{}")       # 光影语言
    material = Column(Text, default="")      # 材质表现
    layout = Column(Text, default="{}")      # 排版
    typography = Column(Text, default="{}")  # 文字 / 标题 / 字体
    style = Column(Text, default="{}")       # 视觉风格 JSON
    design_rules = Column(Text, default="{}")  # 设计规则
    insights = Column(Text, default="")      # VLM 深度解析 JSON
    analyzed_by = Column(String, default="启发式规则")  # 语义来源
    prompt = Column(Text, default="")        # AI 绘图提示词
    version = Column(Integer, default=1)
    confidence = Column(Integer, default=60)
    model_name = Column(String, default="")
    prompt_version = Column(String, default="visual-analysis-v1")
    generation_mode = Column(String, default="heuristic_fallback", index=True)
    review_status = Column(String, default="ai_unverified")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    case = relationship("Case", back_populates="analysis")


class AnalysisVersion(Base):
    """每次 AI 生成或人工修订的完整快照。"""

    __tablename__ = "analysis_versions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version = Column(Integer, nullable=False)
    payload = Column(Text, default="{}")
    source = Column(String, default="ai")  # ai / manual / regenerate
    model_name = Column(String, default="")
    prompt_version = Column(String, default="visual-analysis-v1")
    editor = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class LayoutBlueprint(Base):
    """Versioned, normalized low-fidelity layout skeleton for one case."""

    __tablename__ = "layout_blueprints"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "version",
            name="uq_layout_blueprints_case_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canvas_ratio = Column(String, default="1:1")
    orientation = Column(String, default="square", index=True)
    grid_columns = Column(Integer, default=1)
    grid_rows = Column(Integer, default=1)
    margins = Column(Text, default="{}")
    margins_json = Column(Text, default="{}")
    alignment = Column(String, default="")
    reading_flow = Column(String, default="")
    focal_region = Column(Text, default="{}")
    information_density = Column(String, default="")
    text_image_ratio = Column(Float, default=0.5)
    module_count = Column(Integer, default=0)
    modules_json = Column(Text, default="[]")
    layout_signature = Column(String, default="", index=True)
    version = Column(Integer, default=1, nullable=False, index=True)
    review_status = Column(String, default="ai_generated", index=True)
    model_name = Column(String, default="")
    prompt_version = Column(String, default="layout-blueprint-v1")
    editor = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )

    case = relationship("Case", back_populates="layout_blueprints")


class LayoutPattern(Base):
    """Reusable layout knowledge distilled from one or more verified blueprints."""

    __tablename__ = "layout_patterns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    pattern_code = Column(String, default="", index=True)
    description = Column(Text, default="")
    canvas_ratio = Column(String, default="1:1", index=True)
    orientation = Column(String, default="square", index=True)
    grid_columns = Column(Integer, default=1)
    grid_rows = Column(Integer, default=1)
    margins = Column(Text, default="{}")
    alignment = Column(String, default="", index=True)
    reading_flow = Column(String, default="")
    layout_signature = Column(String, default="", index=True)
    focal_region = Column(Text, default="")
    information_density = Column(String, default="", index=True)
    text_image_ratio = Column(Float, default=0.5)
    module_count = Column(Integer, default=0)
    modules_json = Column(Text, default="[]")
    module_structure_json = Column(Text, default="[]")
    average_positions_json = Column(Text, default="[]")
    required_modules_json = Column(Text, default="[]")
    optional_modules_json = Column(Text, default="[]")
    suitable_scenes_json = Column(Text, default="[]")
    unsuitable_scenes_json = Column(Text, default="[]")
    evidence_case_ids_json = Column(Text, default="[]")
    evidence_blueprint_ids_json = Column(Text, default="[]")
    evidence_count = Column(Integer, default=0)
    confidence_level = Column(String, default="candidate", index=True)
    discovery_method = Column(String, default="", index=True)
    generated_at = Column(DateTime, nullable=True)
    source_blueprint_ids = Column(Text, default="[]")
    source_case_ids = Column(Text, default="[]")
    industry_tags = Column(Text, default="[]")
    scene_tags = Column(Text, default="[]")
    channel_tags = Column(Text, default="[]")
    business_goal_tags = Column(Text, default="[]")
    product_category_tags_json = Column(Text, default="[]")
    content_purpose_tags_json = Column(Text, default="[]")
    campaign_stage_tags_json = Column(Text, default="[]")
    business_context_json = Column(Text, default="{}")
    business_context_review_status = Column(String, default="suggested", index=True)
    business_context_reviewer = Column(String, default="")
    source_candidate_id = Column(String, default="")
    source_candidate_ids_json = Column(Text, default="[]")
    evidence_annotation_ids_json = Column(Text, default="[]")
    usage_notes = Column(Text, default="")
    version = Column(Integer, default=1, nullable=False)
    review_status = Column(String, default="human_edited", index=True)
    reviewer = Column(String, default="")
    model_name = Column(String, default="")
    prompt_version = Column(String, default="layout-pattern-v1")
    editor = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class LayoutPatternCandidateReview(Base):
    """Independent candidate decision, owner confirmation and formal state."""

    __tablename__ = "layout_pattern_candidate_reviews"

    candidate_id = Column(String, primary_key=True)
    decision = Column(String, default="pending", nullable=False, index=True)
    owner_confirmed = Column(Boolean, default=False, nullable=False, index=True)
    owner_reviewer = Column(String, default="")
    merge_target_id = Column(String, default="", index=True)
    display_name = Column(String, default="")
    formal_pattern_id = Column(Integer, ForeignKey("layout_patterns.id"), nullable=True, unique=True)
    formal_status = Column(String, default="not_created", nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class LayoutPatternCandidateReviewEvent(Base):
    """Append-only audit trail for candidate review and formal publication."""

    __tablename__ = "layout_pattern_candidate_review_events"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    previous_state = Column(Text, default="{}")
    new_state = Column(Text, default="{}")
    merge_target_id = Column(String, default="")
    formal_pattern_id = Column(Integer, nullable=True, index=True)
    reviewer = Column(String, default="")
    reviewer_role = Column(String, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class PairingAuthorizationEvent(Base):
    """Owner authorization for an automatic pairing; never rewrites detection provenance."""

    __tablename__ = "pairing_authorization_events"
    __table_args__ = (
        UniqueConstraint(
            "annotation_id", "authorization_status", "authorization_reason",
            name="uq_pairing_authorization_event",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    annotation_id = Column(
        Integer, ForeignKey("disinfection_annotations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    pairing_detection_source = Column(String, nullable=False, index=True)
    authorization_status = Column(String, nullable=False, index=True)
    authorized_by = Column(String, nullable=False)
    authorization_reason = Column(String, nullable=False, index=True)
    evidence_json = Column(Text, default="{}")
    authorized_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class LayoutBlueprintVerificationEvent(Base):
    """Append-only evidence explaining a human-confirmed blueprint version."""

    __tablename__ = "layout_blueprint_verification_events"
    __table_args__ = (
        UniqueConstraint(
            "blueprint_id", "verification_source",
            name="uq_layout_blueprint_verification_event",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    blueprint_id = Column(
        Integer, ForeignKey("layout_blueprints.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_pattern_ids_json = Column(Text, default="[]")
    reviewer = Column(String, nullable=False)
    verification_source = Column(String, nullable=False, index=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class BusinessRequirement(Base):
    """Structured, persisted real-world brief used for layout retrieval."""

    __tablename__ = "business_requirements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    request_text = Column(Text, default="")
    industry = Column(String, default="", index=True)
    product_category = Column(String, default="", index=True)
    channel = Column(String, default="", index=True)
    canvas_ratio = Column(String, default="", index=True)
    orientation = Column(String, default="", index=True)
    campaign_stage = Column(String, default="", index=True)
    business_goal = Column(Text, default="")
    target_audience = Column(Text, default="")
    content_purpose = Column(String, default="", index=True)
    required_modules_json = Column(Text, default="[]")
    optional_modules_json = Column(Text, default="[]")
    forbidden_modules_json = Column(Text, default="[]")
    selling_points_json = Column(Text, default="[]")
    style_keywords_json = Column(Text, default="[]")
    raw_requirement = Column(Text, default="")
    reference_case_ids_json = Column(Text, default="[]")
    reference_image_path = Column(Text, default="")
    creator = Column(String, default="")
    key_message = Column(Text, default="")
    mandatory_elements = Column(Text, default="[]")
    information_density = Column(String, default="", index=True)
    reference_case_ids = Column(Text, default="[]")
    created_by = Column(String, default="")
    status = Column(String, default="draft", index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class RequirementReferenceAnalysis(Base):
    """Cached temporary blueprint for a requirement reference image."""

    __tablename__ = "requirement_reference_analyses"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_path = Column(Text, nullable=False)
    blueprint_json = Column(Text, default="{}")
    model_name = Column(String, default="")
    prompt_version = Column(String, default="requirement-reference-layout-v1")
    generation_mode = Column(String, default="heuristic_fallback", index=True)
    failure_reason = Column(Text, default="")
    image_sha256 = Column(String, default="", index=True)
    analyzer_version = Column(String, default="reference-layout-v2", index=True)
    analysis_status = Column(String, default="completed", index=True)
    verified_by = Column(String, default="")
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class LayoutSearchRun(Base):
    """Immutable query/result snapshot used only for retrieval evaluation."""

    __tablename__ = "layout_search_runs"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_snapshot_json = Column(Text, default="{}")
    result_snapshot_json = Column(Text, default="{}")
    scoring_version = Column(String, default="layout-search-rules-v1", index=True)
    reference_analysis_id = Column(
        Integer,
        ForeignKey("requirement_reference_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    elapsed_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class LayoutSearchFeedback(Base):
    """Human relevance judgment for one result in one retrieval run."""

    __tablename__ = "layout_search_feedback"

    id = Column(Integer, primary_key=True, index=True)
    search_run_id = Column(
        Integer,
        ForeignKey("layout_search_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    result_type = Column(String, nullable=False, index=True)
    result_id = Column(Integer, nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    relevance = Column(String, nullable=False, index=True)
    reviewer = Column(String, nullable=False, index=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class LayoutSearchGroundTruth(Base):
    """Frozen pre-retrieval relevance label for acceptance evaluation."""

    __tablename__ = "layout_search_ground_truth"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id", "result_type", "result_id", "dataset_version",
            name="uq_layout_search_ground_truth_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    result_type = Column(String, nullable=False, index=True)
    result_id = Column(Integer, nullable=False, index=True)
    expected_relevance = Column(String, nullable=False, index=True)
    reviewer = Column(String, nullable=False)
    reason = Column(Text, default="")
    dataset_version = Column(String, nullable=False, index=True)
    dataset_split = Column(String, nullable=False, index=True)
    frozen_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class LayoutSearchDataset(Base):
    """Acceptance dataset metadata; labels remain in the immutable GT table."""

    __tablename__ = "layout_search_datasets"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    dataset_kind = Column(String, default="real", nullable=False, index=True)
    created_by = Column(String, nullable=False)
    frozen_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class AnalysisEvaluationDataset(Base):
    """Versioned image-decomposition dataset, separate from retrieval acceptance."""

    __tablename__ = "analysis_evaluation_datasets"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    product_category = Column(String, default="", index=True)
    description = Column(Text, default="")
    status = Column(String, default="draft", nullable=False, index=True)
    created_by = Column(String, nullable=False)
    sealed_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class AnalysisEvaluationItem(Base):
    """Ground-truth assignment for one case in exactly one dataset split."""

    __tablename__ = "analysis_evaluation_items"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "case_id", name="uq_analysis_dataset_case"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("analysis_evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id = Column(
        Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_split = Column(String, nullable=False, index=True)
    ground_truth_json = Column(Text, default="{}")
    gt_status = Column(String, default="pending", nullable=False, index=True)
    reviewer = Column(String, default="")
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class AnalysisRuntimeVersion(Base):
    """Immutable Prompt/Validator bundle used by calibration and holdout runs."""

    __tablename__ = "analysis_runtime_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_name",
            "prompt_version",
            "validator_version",
            name="uq_analysis_runtime_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, nullable=False, index=True)
    model_provider = Column(String, nullable=False, default="")
    prompt_version = Column(String, nullable=False, index=True)
    prompt_text = Column(Text, default="")
    prompt_hash = Column(String, nullable=False, index=True)
    validator_version = Column(String, nullable=False, index=True)
    validator_config_json = Column(Text, default="{}")
    validator_hash = Column(String, nullable=False, index=True)
    status = Column(String, default="draft", nullable=False, index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    frozen_at = Column(DateTime, nullable=True)


class AnalysisEvaluationRun(Base):
    """Immutable execution and version snapshot for one dataset split."""

    __tablename__ = "analysis_evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "dataset_split",
            "runtime_version_id",
            "formal",
            name="uq_analysis_formal_run_combination",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("analysis_evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_split = Column(String, nullable=False, index=True)
    runtime_version_id = Column(
        Integer,
        ForeignKey("analysis_runtime_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    formal = Column(Boolean, default=False, nullable=False, index=True)
    run_status = Column(String, default="queued", nullable=False, index=True)
    aggregate_json = Column(Text, default="{}")
    version_snapshot_json = Column(Text, default="{}")
    error_code = Column(String, default="", index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    elapsed_ms = Column(Integer, default=0)
    unsealed_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class AnalysisEvaluationResult(Base):
    """Per-case result. Holdout details are protected by the API boundary."""

    __tablename__ = "analysis_evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "item_id", name="uq_analysis_run_item_result"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("analysis_evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        Integer,
        ForeignKey("analysis_evaluation_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String, default="pending", nullable=False, index=True)
    error_code = Column(String, default="", index=True)
    metrics_json = Column(Text, default="{}")
    prediction_json = Column(Text, default="{}")
    elapsed_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class LayoutDirection(Base):
    """One generated low-fidelity direction tied to evidence and a brief."""

    __tablename__ = "layout_directions"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_version = Column(Integer, default=1, nullable=False, index=True)
    strategy_level = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    rationale = Column(Text, default="")
    applicable_reason = Column(Text, default="")
    canvas_ratio = Column(String, default="1:1")
    orientation = Column(String, default="square")
    grid_columns = Column(Integer, default=1)
    grid_rows = Column(Integer, default=1)
    margins = Column(Text, default="{}")
    alignment = Column(String, default="")
    reading_flow = Column(String, default="")
    focal_region = Column(Text, default="")
    information_density = Column(String, default="")
    text_image_ratio = Column(Float, default=0.5)
    module_count = Column(Integer, default=0)
    modules_json = Column(Text, default="[]")
    source_pattern_ids = Column(Text, default="[]")
    source_case_ids = Column(Text, default="[]")
    model_name = Column(String, default="")
    prompt_version = Column(String, default="layout-direction-v1")
    generation_mode = Column(String, default="heuristic")
    failure_reason = Column(Text, default="")
    status = Column(String, default="generated", index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class LayoutDirectionFeedback(Base):
    """Append-only selection and adjustment outcome for one direction."""

    __tablename__ = "layout_direction_feedback"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("business_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction_id = Column(
        Integer,
        ForeignKey("layout_directions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False, index=True)
    notes = Column(Text, default="")
    adjusted_modules_json = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Project(Base):
    """A curated business project grouping cases and golden-standard assets."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    business_line = Column(String, default="", index=True)
    status = Column(String, default="active", index=True)
    is_gold = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    cases = relationship("Case", back_populates="project")
    reviews = relationship("CaseReview", back_populates="project")
    preference_events = relationship("PreferenceEvent", back_populates="project")


# Legacy compatibility models below (project review, preference, training,
# company profile and service run) remain for historical data. They are not
# inputs to LayoutPattern discovery or the current formal product workflow.
class CaseReview(Base):
    """Append-only human decisions and corrected analysis snapshots."""

    __tablename__ = "case_reviews"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewer = Column(String, nullable=False, index=True)
    action = Column(String, default="edit", index=True)
    trust_status = Column(String, default="verified", index=True)
    decision = Column(String, default="")
    notes = Column(Text, default="")
    keep_reasons = Column(Text, default="[]")
    avoid_reasons = Column(Text, default="[]")
    corrected_payload = Column(Text, default="{}")
    analysis_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case")
    project = relationship("Project", back_populates="reviews")


class AssetCategorySuggestion(Base):
    """Model-proposed primary learning category, pending human confirmation."""

    __tablename__ = "asset_category_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    suggested_category = Column(String, nullable=False, index=True)
    confidence = Column(Integer, default=0)
    reason = Column(Text, default="")
    signals = Column(Text, default="[]")
    model_name = Column(String, default="")
    status = Column(String, default="pending", index=True)
    reviewer = Column(String, default="")
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case")


class CategorySuggestionJob(Base):
    """Observable background batch for long-running vision classification."""

    __tablename__ = "category_suggestion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    case_ids = Column(Text, default="[]")
    status = Column(String, default="queued", index=True)
    total = Column(Integer, default=0)
    completed = Column(Integer, default=0)
    succeeded = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    errors = Column(Text, default="[]")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class BatchImportJob(Base):
    """Persisted, restart-surviving progress for one bulk asset import."""

    __tablename__ = "batch_import_jobs"

    id = Column(String, primary_key=True, index=True)  # uuid hex = batch_id
    status = Column(String, default="processing", index=True)
    total = Column(Integer, default=0)
    done = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    fallback = Column(Integer, default=0)
    case_ids = Column(Text, default="[]")
    errors = Column(Text, default="[]")
    skipped_files = Column(Text, default="[]")
    concurrency = Column(Integer, default=1)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class PreferenceEvent(Base):
    """Legacy preference evidence; never read by LayoutPattern discovery."""
    """Explicit business preference signals used for weighted style profiles."""

    __tablename__ = "preference_events"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    value = Column(Integer, default=1)
    actor = Column(String, default="")
    context = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case")
    project = relationship("Project", back_populates="preference_events")


class ServiceRun(Base):
    """Legacy service-run history; excluded from the formal pattern pipeline."""
    """A persisted recommendation output and its eventual business outcome."""

    __tablename__ = "service_runs"

    id = Column(Integer, primary_key=True, index=True)
    request_text = Column(Text, default="")
    industry = Column(String, default="", index=True)
    channel = Column(String, default="", index=True)
    campaign_stage = Column(String, default="", index=True)
    focus_category = Column(String, default="layout", index=True)
    business_goal = Column(Text, default="")
    result_payload = Column(Text, default="{}")
    evidence_case_ids = Column(Text, default="[]")
    company_profile_snapshot = Column(Text, default="{}")
    status = Column(String, default="generated", index=True)
    actor = Column(String, default="")
    feedback = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class Tag(Base):
    """标签表：支持分类与层级关系。"""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, default="style")  # 分类：style/industry/scene/mood...
    parent_id = Column(Integer, ForeignKey("tags.id"), nullable=True)  # 层级关系

    cases = relationship("Case", secondary=case_tags, back_populates="tags")


class DisinfectionAnnotationBatch(Base):
    """One idempotent import of annotated disinfection-cabinet artwork."""

    __tablename__ = "disinfection_annotation_batches"

    id = Column(String, primary_key=True)
    source_root = Column(String, default="")
    status = Column(String, default="pending_review", index=True)
    scan_report_json = Column(Text, default="{}")
    total = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class DisinfectionAnnotation(Base):
    """Human-reviewable colored-box annotation; never truth until verified."""

    __tablename__ = "disinfection_annotations"
    __table_args__ = (UniqueConstraint("source_sha256", name="uq_disinfection_annotation_sha"),)

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String, ForeignKey("disinfection_annotation_batches.id"), index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    annotated_image_path = Column(String, default="")
    original_image_path = Column(String, default="")
    source_sha256 = Column(String, nullable=False, index=True)
    source_type = Column(String, default="company_published", index=True)
    product_category = Column(String, default="消毒柜", index=True)
    project_key = Column(String, default="", index=True)
    page_role = Column(String, default="other", index=True)
    sequence_index = Column(Integer, nullable=True)
    canvas_width = Column(Integer, default=0)
    canvas_height = Column(Integer, default=0)
    orientation = Column(String, default="portrait")
    regions_json = Column(Text, default="[]")
    warnings_json = Column(Text, default="[]")
    status = Column(String, default="pending_review", index=True)
    annotation_verified = Column(Boolean, nullable=True, index=True)
    company_recommended = Column(Boolean, nullable=True, index=True)
    recommendation_status = Column(String, default="unknown", index=True)
    not_recommended_reason = Column(Text, default="")
    avoid_reasons_json = Column(Text, default="[]")
    keep_reasons_json = Column(Text, default="[]")
    recommendation_reviewer = Column(String, default="")
    recommendation_confirmed_by_lead = Column(Boolean, default=False)
    recommendation_reviewed_at = Column(DateTime, nullable=True)
    curator_selected_good = Column(Boolean, default=False, index=True)
    curator_selection_reason = Column(Text, default="")
    structure_review_status = Column(String, default="", index=True)
    structure_review_json = Column(Text, default="{}")
    structure_cluster_key = Column(String, default="", index=True)
    dataset_split = Column(String, default="", index=True)
    reviewer = Column(String, default="")
    reviewed_at = Column(DateTime, nullable=True)
    annotation_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class CompanyEvidenceRepairAudit(Base):
    """Append-only proof for a tightly constrained company-evidence repair."""

    __tablename__ = "company_evidence_repair_audits"
    __table_args__ = (
        UniqueConstraint("annotation_id", "original_sha256", name="uq_company_evidence_repair"),
    )

    id = Column(Integer, primary_key=True)
    annotation_id = Column(Integer, ForeignKey("disinfection_annotations.id", ondelete="RESTRICT"), index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="RESTRICT"), index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="RESTRICT"), index=True)
    original_sha256 = Column(String, nullable=False, index=True)
    near_duplicate_override = Column(Boolean, default=True, nullable=False)
    near_duplicate_case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    perceptual_hash_distance = Column(Integer, nullable=True)
    evidence_paths_json = Column(Text, default="[]")
    reviewer = Column(String, nullable=False)
    repair_reason = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class DisinfectionAnnotationVersion(Base):
    __tablename__ = "disinfection_annotation_versions"
    __table_args__ = (
        UniqueConstraint("annotation_id", "version", name="uq_disinfection_annotation_version"),
    )

    id = Column(Integer, primary_key=True)
    annotation_id = Column(
        Integer, ForeignKey("disinfection_annotations.id", ondelete="CASCADE"), index=True
    )
    version = Column(Integer, nullable=False)
    payload_json = Column(Text, default="{}")
    source = Column(String, default="parser")
    editor = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class DisinfectionDecompositionRun(Base):
    """Trace one few-shot-assisted attempt on an unannotated company image."""

    __tablename__ = "disinfection_decomposition_runs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    blueprint_id = Column(
        Integer, ForeignKey("layout_blueprints.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(String, default="review_required", index=True)
    evidence_annotation_ids_json = Column(Text, default="[]")
    initial_ai_blueprint_json = Column(Text, default="{}")
    final_blueprint_json = Column(Text, default="{}")
    failure_reasons_json = Column(Text, default="[]")
    model_name = Column(String, default="")
    prompt_version = Column(String, default="disinfection-layout-few-shot-v1")
    generation_mode = Column(String, default="model")
    manual_edit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)
