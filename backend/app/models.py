"""第一阶段数据库模型。

核心闭环：素材进入 → AI 拆解 → 多模态检索 → 案例选择。
保留旧仓库的 images / cases / analysis / tags 关系，补齐来源治理、可信状态、
模型版本和分析版本记录，便于后续迁移到 PostgreSQL。
"""
import datetime as dt

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
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
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case", back_populates="image", uselist=False)


class Case(Base):
    """案例表：一张图片拆解后形成的「案例资产卡」。"""

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    content_type = Column(String, default="", index=True)
    product_category = Column(String, default="", index=True)
    industry = Column(String, default="")        # 行业
    scene = Column(String, default="")           # 使用场景
    summary = Column(Text, default="")           # 一句话总结
    trust_status = Column(String, default="ai_unverified", index=True)
    status = Column(String, default="public", index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    image = relationship("Image", back_populates="case")
    analysis = relationship(
        "Analysis", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    tags = relationship("Tag", secondary=case_tags, back_populates="cases")


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


class Tag(Base):
    """标签表：支持分类与层级关系。"""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, default="style")  # 分类：style/industry/scene/mood...
    parent_id = Column(Integer, ForeignKey("tags.id"), nullable=True)  # 层级关系

    cases = relationship("Case", secondary=case_tags, back_populates="tags")
