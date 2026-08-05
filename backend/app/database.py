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
            "generation_mode": "heuristic_fallback",
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
            "product_name": "",
            "content_purpose": "",
            "page_role": "other",
            "brief_ref": "",
            "metadata_status": "inferred",
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
        if "sequence_index" not in case_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN sequence_index INTEGER"))
        if "reviewed_at" not in case_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN reviewed_at DATETIME"))
        for col in ("blueprint_correct", "business_reusable"):
            if col not in case_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(f"ALTER TABLE cases ADD COLUMN {col} INTEGER DEFAULT 0")
                    )
        if "project_id" not in case_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN project_id INTEGER"))
    if "service_runs" in tables:
        run_cols = {c["name"] for c in inspector.get_columns("service_runs")}
        run_fields = {
            "channel": "",
            "campaign_stage": "",
            "focus_category": "layout",
            "business_goal": "",
        }
        for col, default in run_fields.items():
            if col not in run_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE service_runs ADD COLUMN {col} "
                            f"TEXT DEFAULT '{default}'"
                        )
                    )
    if "case_reviews" in tables:
        review_cols = {c["name"] for c in inspector.get_columns("case_reviews")}
        for col in ("keep_reasons", "avoid_reasons"):
            if col not in review_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE case_reviews ADD COLUMN {col} "
                            "TEXT DEFAULT '[]'"
                        )
                    )
    if "batch_import_jobs" in tables:
        job_cols = {c["name"] for c in inspector.get_columns("batch_import_jobs")}
        if "fallback" not in job_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE batch_import_jobs ADD COLUMN fallback INTEGER DEFAULT 0")
                )
    if "disinfection_annotations" in tables:
        annotation_cols = {
            c["name"] for c in inspector.get_columns("disinfection_annotations")
        }
        annotation_fields = {
            "annotation_verified": ("INTEGER", None),
            "company_recommended": ("INTEGER", None),
            "recommendation_status": ("TEXT", "unknown"),
            "not_recommended_reason": ("TEXT", ""),
            "avoid_reasons_json": ("TEXT", "[]"),
            "keep_reasons_json": ("TEXT", "[]"),
            "recommendation_reviewer": ("TEXT", ""),
            "recommendation_confirmed_by_lead": ("INTEGER", "0"),
            "curator_selected_good": ("INTEGER", "0"),
            "curator_selection_reason": ("TEXT", ""),
            "structure_review_status": ("TEXT", ""),
            "structure_review_json": ("TEXT", "{}"),
            "structure_cluster_key": ("TEXT", ""),
        }
        for col, (col_type, default) in annotation_fields.items():
            if col not in annotation_cols:
                default_sql = "" if default is None else f" DEFAULT '{default}'"
                with engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE disinfection_annotations ADD COLUMN {col} "
                        f"{col_type}{default_sql}"
                    ))
        if "recommendation_reviewed_at" not in annotation_cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE disinfection_annotations "
                    "ADD COLUMN recommendation_reviewed_at DATETIME"
                ))
    if "layout_blueprints" in tables:
        blueprint_cols = {
            c["name"] for c in inspector.get_columns("layout_blueprints")
        }
        blueprint_fields = {
            "canvas_ratio": ("TEXT", "1:1"),
            "orientation": ("TEXT", "square"),
            "grid_columns": ("INTEGER", "1"),
            "grid_rows": ("INTEGER", "1"),
            "margins": ("TEXT", "{}"),
            "margins_json": ("TEXT", "{}"),
            "alignment": ("TEXT", ""),
            "reading_flow": ("TEXT", ""),
            "focal_region": ("TEXT", "{}"),
            "information_density": ("TEXT", ""),
            "text_image_ratio": ("REAL", "0.5"),
            "module_count": ("INTEGER", "0"),
            "modules_json": ("TEXT", "[]"),
            "layout_signature": ("TEXT", ""),
            "version": ("INTEGER", "1"),
            "review_status": ("TEXT", "ai_unverified"),
            "model_name": ("TEXT", ""),
            "prompt_version": ("TEXT", "layout-blueprint-v1"),
            "editor": ("TEXT", ""),
        }
        for col, (col_type, default) in blueprint_fields.items():
            if col not in blueprint_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE layout_blueprints ADD COLUMN {col} "
                            f"{col_type} DEFAULT '{default}'"
                        )
                    )
        for col in ("created_at", "updated_at"):
            if col not in blueprint_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE layout_blueprints "
                            f"ADD COLUMN {col} DATETIME"
                        )
                    )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE layout_blueprints SET review_status='ai_generated' "
                    "WHERE review_status='ai_unverified'"
                )
            )
            conn.execute(
                text(
                    "UPDATE layout_blueprints SET review_status='corrected' "
                    "WHERE review_status='human_edited'"
                )
            )
    if "business_requirements" in tables:
        requirement_cols = {
            c["name"] for c in inspector.get_columns("business_requirements")
        }
        requirement_fields = {
            "content_purpose": ("TEXT", ""),
            "required_modules_json": ("TEXT", "[]"),
            "optional_modules_json": ("TEXT", "[]"),
            "forbidden_modules_json": ("TEXT", "[]"),
            "selling_points_json": ("TEXT", "[]"),
            "style_keywords_json": ("TEXT", "[]"),
            "raw_requirement": ("TEXT", ""),
            "reference_case_ids_json": ("TEXT", "[]"),
            "reference_image_path": ("TEXT", ""),
            "creator": ("TEXT", ""),
        }
        for col, (col_type, default) in requirement_fields.items():
            if col not in requirement_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE business_requirements ADD COLUMN {col} "
                            f"{col_type} DEFAULT '{default}'"
                        )
                    )
    if "layout_patterns" in tables:
        pattern_cols = {
            c["name"] for c in inspector.get_columns("layout_patterns")
        }
        pattern_fields = {
            "pattern_code": ("TEXT", ""),
            "layout_signature": ("TEXT", ""),
            "module_structure_json": ("TEXT", "[]"),
            "average_positions_json": ("TEXT", "[]"),
            "required_modules_json": ("TEXT", "[]"),
            "optional_modules_json": ("TEXT", "[]"),
            "suitable_scenes_json": ("TEXT", "[]"),
            "unsuitable_scenes_json": ("TEXT", "[]"),
            "evidence_case_ids_json": ("TEXT", "[]"),
            "evidence_blueprint_ids_json": ("TEXT", "[]"),
            "evidence_count": ("INTEGER", "0"),
            "confidence_level": ("TEXT", "candidate"),
            "discovery_method": ("TEXT", ""),
            "reviewer": ("TEXT", ""),
            "product_category_tags_json": ("TEXT", "[]"),
            "content_purpose_tags_json": ("TEXT", "[]"),
            "campaign_stage_tags_json": ("TEXT", "[]"),
            "business_context_json": ("TEXT", "{}"),
            "business_context_review_status": ("TEXT", "suggested"),
            "business_context_reviewer": ("TEXT", ""),
            "source_candidate_id": ("TEXT", ""),
            "source_candidate_ids_json": ("TEXT", "[]"),
            "evidence_annotation_ids_json": ("TEXT", "[]"),
        }
        for col, (col_type, default) in pattern_fields.items():
            if col not in pattern_cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE layout_patterns ADD COLUMN {col} "
                            f"{col_type} DEFAULT '{default}'"
                        )
                    )
        if "generated_at" not in pattern_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE layout_patterns "
                        "ADD COLUMN generated_at DATETIME"
                    )
                )
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_layout_patterns_source_candidate_id "
                "ON layout_patterns (source_candidate_id) WHERE source_candidate_id != ''"
            ))
    if "requirement_reference_analyses" in tables:
        ref_cols = {
            c["name"] for c in inspector.get_columns(
                "requirement_reference_analyses"
            )
        }
        ref_fields = {
            "image_sha256": ("TEXT", ""),
            "analyzer_version": ("TEXT", "reference-layout-v2"),
            "analysis_status": ("TEXT", "completed"),
            "verified_by": ("TEXT", ""),
        }
        for col, (col_type, default) in ref_fields.items():
            if col not in ref_cols:
                with engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE requirement_reference_analyses "
                        f"ADD COLUMN {col} {col_type} DEFAULT '{default}'"
                    ))
        if "verified_at" not in ref_cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE requirement_reference_analyses "
                    "ADD COLUMN verified_at DATETIME"
                ))
