"""数据库连接与会话管理。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  确保模型被注册

    Base.metadata.create_all(bind=engine)
    _enable_wal()
    _auto_migrate()


def close_db():
    """Release pooled database connections during application shutdown."""
    engine.dispose()


def _enable_wal():
    """SQLite 开启 WAL，减少并发批量写入时的锁竞争。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=10000"))
    except Exception:
        pass


def _auto_migrate():
    """轻量迁移：为已存在的旧表补齐新增列（避免升级后需手动删库）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "analysis" in tables:
        existing = {c["name"] for c in inspector.get_columns("analysis")}
        new_cols = {
            "material": "",
            "layout": "{}",
            "typography": "{}",
            "insights": "",
            "analyzed_by": "启发式规则",
            "version": "1",
            "confidence": "60",
            "model_name": "",
            "prompt_version": "visual-analysis-v1",
            "review_status": "ai_unverified",
        }
        for col, default in new_cols.items():
            if col not in existing:
                col_type = "INTEGER" if col in {"version", "confidence"} else "TEXT"
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE analysis ADD COLUMN {col} "
                            f"{col_type} DEFAULT '{default}'"
                        )
                    )
        for col in ("created_at", "updated_at"):
            if col not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE analysis ADD COLUMN {col} DATETIME"))
    if "images" in tables:
        img_cols = {c["name"] for c in inspector.get_columns("images")}
        if "phash" not in img_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE images ADD COLUMN phash TEXT DEFAULT ''"))
        image_fields = {
            "source_type": "external_reference",
            "source_url": "",
            "rights_note": "",
            "visibility": "team",
        }
        for col, default in image_fields.items():
            if col not in img_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(f"ALTER TABLE images ADD COLUMN {col} TEXT DEFAULT '{default}'")
                    )
    if "cases" in tables:
        case_cols = {c["name"] for c in inspector.get_columns("cases")}
        case_fields = {
            "content_type": "",
            "product_category": "",
            "asset_category": "layout",
            "asset_subcategory": "",
            "business_line": "",
            "channel": "",
            "campaign_stage": "",
            "business_goal": "",
            "review_decision": "",
            "review_notes": "",
            "reviewer": "",
            "trust_status": "ai_unverified",
            "status": "public",
        }
        for col, default in case_fields.items():
            if col not in case_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(f"ALTER TABLE cases ADD COLUMN {col} TEXT DEFAULT '{default}'")
                    )
        if "reviewed_at" not in case_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN reviewed_at DATETIME"))
        if "project_id" not in case_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN project_id INTEGER"))
