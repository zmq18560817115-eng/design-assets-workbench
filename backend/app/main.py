"""FastAPI 应用入口（对应技术方案「三、系统整体架构」的后端 API 层）。"""
from __future__ import annotations

import os
import json
import hashlib
import tempfile
import uuid
import datetime as dt
import mimetypes
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image as PILImage

from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    Header,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import (
    acceptance_pack, analysis_evaluation, batch, concept, config, crud, imagehash, layout_patterns, layout_search,
    llm, models, overlay, vlm,
    acceptance_pack, batch, concept, config, crud, imagehash, layout_blueprint, layout_patterns, layout_search,
    disinfection_annotations, llm, models, overlay, provider_workflow, vlm,
)
from .asset_categories import category_focus, category_label, normalize_category
from .business_contract import normalize_new_source_type, normalize_page_role
from . import platform as plat
from . import search as multimodal_search
from .agents import run_pipeline
from .database import SessionLocal, close_db, get_db, init_db
from .schemas import (
    AnalysisResult,
    BusinessRequirementCreate,
    BusinessRequirementUpdate,
    BusinessRequirementMatchOut,
    BusinessRequirementOut,
    CaseOut,
    CaseBusinessUpdate,
    CaseReviewInput,
    CaseProjectInput,
    LayoutBlueprintInput,
    LayoutBlueprintOut,
    LayoutBlueprintVerifyInput,
    LayoutPatternCreate,
    LayoutPatternOut,
    LayoutPatternUpdate,
    LayoutPatternPatch,
    LayoutPatternRebuildInput,
    LayoutPatternVerifyInput,
    LayoutSearchInput,
    LayoutSearchFeedbackCreate,
    LayoutSearchGroundTruthCreate,
    LayoutSearchGroundTruthFreeze,
    LayoutSearchGroundTruthUpdate,
    LayoutSearchEvaluationRunInput,
    LayoutSearchDatasetCreate,
    AnalysisDatasetCreate,
    AnalysisDatasetItemUpsert,
    AnalysisGroundTruthUpdate,
    AnalysisRuntimeVersionCreate,
    AnalysisEvaluationRunCreate,
    AnalysisVersionFreezeInput,
    AnalysisHoldoutUnsealInput,
    AnalysisResultRetryInput,
    ProviderWorkflowStageInput,
    LayoutDirectionOut,
    LayoutDirectionSetOut,
    LayoutDirectionFeedbackCreate,
    LayoutDirectionFeedbackOut,
    BatchReviewInput,
    BatchCategorizeInput,
    BatchCategorySuggestionInput,
    PreferenceEventInput,
    ProjectCreate,
    ProjectOut,
    SearchHit,
    ServiceFeedbackInput,
    VisualDirection,
)

app = FastAPI(
    title="设计灵感资产库 API",
    description="标准化排版拆解、模式沉淀与业务排版意向方向系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态托管上传的图片
app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")


def _annotation_dict(row: models.DisinfectionAnnotation) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "filename": Path(row.annotated_image_path).name,
        "original_image_path": row.original_image_path,
        "image_url": f"/api/layout-annotations/{row.id}/image",
        "original_image_url": (
            f"/api/layout-annotations/{row.id}/original-image"
            if row.original_image_path else ""
        ),
        "source_type": row.source_type,
        "product_category": row.product_category,
        "project_key": row.project_key,
        "page_role": row.page_role,
        "sequence_index": row.sequence_index,
        "canvas_width": row.canvas_width,
        "canvas_height": row.canvas_height,
        "orientation": row.orientation,
        "regions": json.loads(row.regions_json or "[]"),
        "warnings": json.loads(row.warnings_json or "[]"),
        "status": row.status,
        "annotation_verified": bool(row.annotation_verified) or row.status == "verified",
        "annotation_verified_explicit": row.annotation_verified,
        "company_recommended": row.company_recommended,
        "recommendation_status": row.recommendation_status or "unknown",
        "not_recommended_reason": row.not_recommended_reason or "",
        "avoid_reasons": json.loads(row.avoid_reasons_json or "[]"),
        "keep_reasons": json.loads(row.keep_reasons_json or "[]"),
        "recommendation_reviewer": row.recommendation_reviewer or "",
        "recommendation_confirmed_by_lead": bool(row.recommendation_confirmed_by_lead),
        "dataset_split": row.dataset_split,
        "reviewer": row.reviewer,
        "reviewed_at": row.reviewed_at,
        "annotation_version": row.annotation_version,
    }


@app.get("/api/layout-annotations")
@app.get("/api/disinfection-annotations")
def list_disinfection_annotations(
    status: str = "",
    product_category: str = "",
    source_type: str = "",
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(models.DisinfectionAnnotation)
    if status:
        query = query.filter(models.DisinfectionAnnotation.status == status)
    if product_category:
        query = query.filter(
            models.DisinfectionAnnotation.product_category == product_category
        )
    if source_type:
        query = query.filter(models.DisinfectionAnnotation.source_type == source_type)
    rows = query.order_by(models.DisinfectionAnnotation.id).all()
    counts = dict(
        db.query(models.DisinfectionAnnotation.status, func.count(models.DisinfectionAnnotation.id))
        .group_by(models.DisinfectionAnnotation.status)
        .all()
    )
    batch = (
        db.query(models.DisinfectionAnnotationBatch)
        .order_by(models.DisinfectionAnnotationBatch.created_at.desc())
        .first()
    )
    return {
        "items": [_annotation_dict(row) for row in rows],
        "counts": counts,
        "workflow_counts": {
            "pending_parse": 0,
            "pending_review": counts.get("pending_review", 0),
            "verified": counts.get("verified", 0),
            "parse_failed": sum(
                not json.loads(row.regions_json or "[]") for row in rows
            ),
        },
        "total": len(rows),
        "batch": {
            "id": batch.id,
            "source_root": batch.source_root,
            "status": batch.status,
            "total": batch.total,
            "scan_report": json.loads(batch.scan_report_json or "{}"),
        } if batch else None,
    }


@app.get("/api/layout-annotations/{annotation_id}/image")
@app.get("/api/disinfection-annotations/{annotation_id}/image")
def get_disinfection_annotation_image(
    annotation_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(models.DisinfectionAnnotation, annotation_id)
    if not row:
        raise HTTPException(404, "annotation not found")
    path = Path(row.annotated_image_path).resolve()
    workspace = Path(__file__).resolve().parents[2]
    allowed_roots = {
        (workspace / "Untitled").resolve(),
        (workspace / "Untitled1").resolve(),
    }


def _annotation_quality_blockers(row: models.DisinfectionAnnotation) -> list[str]:
    regions = json.loads(row.regions_json or "[]")
    required = set(disinfection_annotations.COLOR_TYPES.values())
    blockers = [f"missing:{kind}" for kind in sorted(required - {r.get("type") for r in regions})]
    for index, region in enumerate(regions):
        x, y = float(region.get("x", -1)), float(region.get("y", -1))
        width, height = float(region.get("width", -1)), float(region.get("height", -1))
        area = width * height
        if min(x, y, width, height) < 0 or x + width > 1.000001 or y + height > 1.000001:
            blockers.append(f"out_of_bounds:{region.get('id', index)}")
        if area < 0.00045 or area > 0.98:
            blockers.append(f"abnormal_area:{region.get('id', index)}")
        for other in regions[index + 1:]:
            if region.get("type") == other.get("type") and disinfection_annotations._iou(region, other) > 0.88:
                blockers.append(f"duplicate:{region.get('id')}:{other.get('id')}")
    return blockers
    batch = db.get(models.DisinfectionAnnotationBatch, row.batch_id) if row.batch_id else None
    if batch and batch.source_root:
        allowed_roots.add(Path(batch.source_root).resolve())
    if not any(root == path or root in path.parents for root in allowed_roots) or not path.is_file():
        raise HTTPException(404, "annotation image unavailable")
    return FileResponse(path)


@app.get("/api/layout-annotations/{annotation_id}/original-image")
@app.get("/api/disinfection-annotations/{annotation_id}/original-image")
def get_disinfection_annotation_original_image(
    annotation_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(models.DisinfectionAnnotation, annotation_id)
    if not row or not row.original_image_path:
        raise HTTPException(404, "paired original image unavailable")
    path = Path(row.original_image_path).resolve()
    workspace = Path(__file__).resolve().parents[2]
    allowed_root = (workspace / "公司成品素材").resolve()
    if allowed_root not in path.parents or not path.is_file():
        raise HTTPException(404, "paired original image unavailable")
    return FileResponse(path)


@app.patch("/api/layout-annotations/{annotation_id}")
@app.patch("/api/disinfection-annotations/{annotation_id}")
def update_disinfection_annotation(
    annotation_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(models.DisinfectionAnnotation, annotation_id)
    if not row:
        raise HTTPException(404, "annotation not found")
    regions = payload.get("regions", json.loads(row.regions_json or "[]"))
    allowed_types = set(disinfection_annotations.COLOR_TYPES.values())
    for region in regions:
        if region.get("type") not in allowed_types:
            raise HTTPException(422, f"invalid region type: {region.get('type')}")
        for key in ("x", "y", "width", "height"):
            value = float(region.get(key, -1))
            if value < 0 or value > 1:
                raise HTTPException(422, f"{key} must be normalized")
        if float(region["x"]) + float(region["width"]) > 1.000001 or float(region["y"]) + float(region["height"]) > 1.000001:
            raise HTTPException(422, "region exceeds canvas")
    snapshot = _annotation_dict(row)
    row.annotation_version += 1
    row.regions_json = json.dumps(regions, ensure_ascii=False)
    if "page_role" in payload:
        try:
            payload["page_role"] = normalize_page_role(str(payload["page_role"]))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    for field in (
        "project_key", "page_role", "sequence_index", "reviewer",
        "original_image_path", "product_category", "source_type",
    ):
        if field in payload:
            setattr(row, field, payload[field])
    if not (row.product_category or "").strip():
        raise HTTPException(422, "product_category is required")
    if row.source_type not in {
        "company_published", "external_reference",
        "rejected_company_design", "company_revision",
    }:
        raise HTTPException(422, "invalid source_type")
    if row.status == "verified":
        row.status = "pending_review"
        row.dataset_split = ""
    db.add(models.DisinfectionAnnotationVersion(
        annotation_id=row.id,
        version=row.annotation_version,
        payload_json=json.dumps(snapshot, ensure_ascii=False, default=str),
        source="manual",
        editor=str(payload.get("reviewer") or row.reviewer),
    ))
    db.commit()
    db.refresh(row)
    return _annotation_dict(row)


@app.post("/api/layout-annotations/{annotation_id}/verify")
@app.post("/api/disinfection-annotations/{annotation_id}/verify")
def verify_disinfection_annotation(
    annotation_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(models.DisinfectionAnnotation, annotation_id)
    if not row:
        raise HTTPException(404, "annotation not found")
    reviewer = str(payload.get("reviewer") or "").strip()
    if not reviewer:
        raise HTTPException(422, "reviewer is required")
    if payload.get("pairing_confirmed") is not True:
        raise HTTPException(422, "pairing confirmation is required")
    if payload.get("boxes_confirmed") is not True:
        raise HTTPException(422, "red/blue/green box confirmation is required")
    if payload.get("page_role_confirmed") is not True:
        raise HTTPException(422, "page_role confirmation is required")
    reading_order = payload.get("reading_order")
    if not isinstance(reading_order, list) or not reading_order or any(
        not str(item).strip() for item in reading_order
    ):
        raise HTTPException(422, "reading_order is required")
    region_ids = [str(region.get("id") or "").strip() for region in json.loads(row.regions_json or "[]")]
    normalized_order = [str(item).strip() for item in reading_order]
    if len(normalized_order) != len(set(normalized_order)) or set(normalized_order) != set(region_ids):
        raise HTTPException(422, "reading_order must contain every region exactly once")
    quality_blockers = _annotation_quality_blockers(row)
    if quality_blockers:
        raise HTTPException(422, f"needs_box_fix: {', '.join(quality_blockers)}")
    if not (row.project_key or "").strip():
        raise HTTPException(
            422,
            "project_key is required before verification to prevent calibration/holdout leakage",
        )
    row.reviewer = reviewer
    row.status = "verified"
    row.annotation_verified = True
    row.reviewed_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    row.annotation_version += 1
    verified_snapshot = _annotation_dict(row)
    verified_snapshot["manual_confirmation"] = {
        "pairing_confirmed": True,
        "boxes_confirmed": True,
        "reading_order": normalized_order,
        "page_role": row.page_role,
    }
    db.add(models.DisinfectionAnnotationVersion(
        annotation_id=row.id,
        version=row.annotation_version,
        payload_json=json.dumps(verified_snapshot, ensure_ascii=False, default=str),
        source="verify",
        editor=reviewer,
    ))
    db.flush()
    verified_rows = (
        db.query(models.DisinfectionAnnotation)
        .filter(
            models.DisinfectionAnnotation.status == "verified",
            models.DisinfectionAnnotation.product_category == row.product_category,
            models.DisinfectionAnnotation.source_type == row.source_type,
        )
        .all()
    )
    for verified_row in verified_rows:
        verified_row.dataset_split = disinfection_annotations.assign_dataset_splits(
            verified_rows
        )[verified_row.id]
    db.commit()
    db.refresh(row)
    return _annotation_dict(row)


@app.post("/api/layout-annotations/{annotation_id}/recommendation")
def set_disinfection_annotation_recommendation(
    annotation_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(models.DisinfectionAnnotation, annotation_id)
    if not row:
        raise HTTPException(404, "annotation not found")
    decision = str(payload.get("decision") or "").strip()
    if decision not in {"recommended", "not_recommended", "pending_lead"}:
        raise HTTPException(422, "invalid recommendation decision")
    reviewer = str(payload.get("reviewer") or "").strip()
    if not reviewer:
        raise HTTPException(422, "reviewer is required")
    lead_confirmed = payload.get("lead_confirmed") is True
    if decision == "recommended":
        if row.source_type != "company_published":
            raise HTTPException(422, "external evidence cannot be company_recommended")
        if not lead_confirmed:
            raise HTTPException(422, "design lead confirmation is required")
        row.company_recommended = True
    elif decision == "not_recommended":
        row.company_recommended = False
    else:
        row.company_recommended = None
    row.recommendation_status = decision
    row.not_recommended_reason = str(payload.get("not_recommended_reason") or "").strip()
    row.avoid_reasons_json = json.dumps(payload.get("avoid_reasons") or [], ensure_ascii=False)
    row.keep_reasons_json = json.dumps(payload.get("keep_reasons") or [], ensure_ascii=False)
    row.recommendation_reviewer = reviewer
    row.recommendation_confirmed_by_lead = lead_confirmed
    row.recommendation_reviewed_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    row.annotation_version += 1
    snapshot = _annotation_dict(row)
    db.add(models.DisinfectionAnnotationVersion(
        annotation_id=row.id,
        version=row.annotation_version,
        payload_json=json.dumps(snapshot, ensure_ascii=False, default=str),
        source="recommendation",
        editor=reviewer,
    ))
    db.commit()
    db.refresh(row)
    return _annotation_dict(row)


@app.get("/api/layout-annotations/report/summary")
@app.get("/api/disinfection-annotations/report/summary")
def disinfection_annotation_summary(
    product_category: str = "",
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(models.DisinfectionAnnotation).all()
    scoped = [
        row for row in rows
        if not product_category or row.product_category == product_category
    ]
    verified = [
        row for row in scoped
        if disinfection_annotations.annotation_is_verified(row)
        and row.source_type == "company_published"
    ]
    pattern_evidence = [
        row for row in scoped
        if disinfection_annotations.eligible_for_company_pattern(row)
    ]
    statistics = disinfection_annotations.verified_statistics(
        rows, product_category=product_category, readiness_threshold=30
    )
    return {
        "status": "ready" if len(verified) >= 30 and any(row.dataset_split == "holdout" for row in verified) else "not_ready",
        "product_category": product_category or "all",
        "total": len(scoped),
        "pending_review": sum(row.status == "pending_review" for row in scoped),
        "verified": len(verified),
        "annotation_verified": len(verified),
        "company_recommended": len(pattern_evidence),
        "recommendation_unknown": sum((row.recommendation_status or "unknown") == "unknown" for row in scoped),
        "few_shot_ready": sum(row.dataset_split == "calibration" for row in pattern_evidence) >= 3,
        "evaluation_ready": len(verified) >= 30 and any(row.dataset_split == "holdout" for row in verified),
        "readiness_threshold": 30,
        "calibration": sum(row.dataset_split == "calibration" for row in verified),
        "holdout": sum(row.dataset_split == "holdout" for row in verified),
        "statistics": statistics,
        "message": "Verified decomposition evidence is separate from lead-confirmed company pattern evidence.",
    }


def _decomposition_run_dict(row: models.DisinfectionDecompositionRun) -> dict:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "blueprint_id": row.blueprint_id,
        "status": row.status,
        "evidence_annotation_ids": json.loads(row.evidence_annotation_ids_json or "[]"),
        "initial_ai_blueprint": json.loads(row.initial_ai_blueprint_json or "{}"),
        "final_blueprint": json.loads(row.final_blueprint_json or "{}"),
        "failure_reasons": json.loads(row.failure_reasons_json or "[]"),
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "generation_mode": row.generation_mode,
        "manual_edit_count": row.manual_edit_count,
        "created_at": row.created_at,
    }


def _find_annotation_original_case(
    db: Session,
    annotation: models.DisinfectionAnnotation,
) -> models.Case | None:
    """Resolve a paired original without crossing product categories.

    Historical imports preserve the display filename, which is not globally
    unique. Exact content identity is preferred; a unique category-scoped
    candidate is the compatibility fallback.
    """
    if not annotation.original_image_path:
        return None
    original_path = Path(annotation.original_image_path)
    candidates = (
        db.query(models.Case)
        .join(models.Image, models.Case.image_id == models.Image.id)
        .filter(
            models.Image.filename == original_path.name,
            models.Image.source_type == "company_published",
            models.Case.product_category == annotation.product_category,
        )
        .all()
    )
    if original_path.is_file():
        expected = hashlib.sha256(original_path.read_bytes()).hexdigest()
        for candidate in candidates:
            uploaded = (config.UPLOAD_DIR / Path(candidate.image.url).name).resolve()
            if (
                uploaded.is_file()
                and hashlib.sha256(uploaded.read_bytes()).hexdigest() == expected
            ):
                return candidate
    return candidates[0] if len(candidates) == 1 else None


@app.get("/api/layout-decomposition-runs")
@app.get("/api/disinfection-decomposition-runs")
def list_disinfection_decomposition_runs(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(models.DisinfectionDecompositionRun)
        .order_by(models.DisinfectionDecompositionRun.id.desc())
        .all()
    )
    return {
        "items": [_decomposition_run_dict(row) for row in rows],
        "counts": dict(Counter(row.status for row in rows)),
    }


@app.post("/api/layout-decomposition-runs/{run_id}/finalize")
@app.post("/api/disinfection-decomposition-runs/{run_id}/finalize")
def finalize_disinfection_decomposition_run(
    run_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    run = db.get(models.DisinfectionDecompositionRun, run_id)
    if not run:
        raise HTTPException(404, "decomposition run not found")
    blueprint_id = int(payload.get("blueprint_id") or run.blueprint_id or 0)
    blueprint = crud.get_layout_blueprint(db, blueprint_id)
    if not blueprint or blueprint.case_id != run.case_id:
        raise HTTPException(422, "final blueprint must belong to the run case")
    if blueprint.review_status != "verified":
        raise HTTPException(422, "final blueprint must be human verified")
    run.final_blueprint_json = json.dumps(
        crud.serialize_layout_blueprint(blueprint), ensure_ascii=False, default=str
    )
    run.manual_edit_count = max(
        0,
        blueprint.version
        - int(json.loads(run.initial_ai_blueprint_json or "{}").get("version", blueprint.version)),
    )
    run.status = "verified"
    db.commit()
    db.refresh(run)
    return _decomposition_run_dict(run)


@app.get("/api/layout-annotations/few-shots")
@app.get("/api/disinfection-annotations/few-shots")
def list_disinfection_few_shots(
    orientation: str = "portrait",
    page_role: str = "",
    product_category: str = "",
    evidence_mode: str = "company",
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(models.DisinfectionAnnotation).all()
    try:
        selected = disinfection_annotations.select_few_shot_annotations(
            rows,
            orientation=orientation,
            page_role=page_role,
            product_category=product_category,
            evidence_mode=evidence_mode,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "items": [
            {
                **_annotation_dict(row),
                "evidence_role": (
                    "company_standard"
                    if row.source_type == "company_published"
                    and (not product_category or row.product_category == product_category)
                    else "cross_category_structure_reference"
                    if row.source_type == "company_published"
                    else "imitation_reference"
                ),
            }
            for row in selected
        ],
        "evidence_annotation_ids": [row.id for row in selected],
        "policy": "exact-category company standards first; cross-category structure second; external references only in imitation mode",
    }


@app.post("/api/cases/{case_id}/layout-auto-decompose")
@app.post("/api/cases/{case_id}/disinfection-auto-decompose")
def auto_decompose_disinfection_case(
    case_id: int,
    db: Session = Depends(get_db),
    evidence_mode: str = "company",
) -> dict:
    case = db.get(models.Case, case_id)
    if not case or not case.image:
        raise HTTPException(404, "case or original image not found")
    image_path = (config.UPLOAD_DIR / Path(case.image.url).name).resolve()
    if not image_path.is_file():
        raise HTTPException(404, "unannotated original image file not found")
    rows = db.query(models.DisinfectionAnnotation).all()
    with PILImage.open(image_path) as source:
        image_width, image_height = source.size
    orientation = (
        "portrait" if image_height > image_width
        else "landscape" if image_width > image_height
        else "square"
    )
    try:
        few_shots = disinfection_annotations.select_few_shot_annotations(
            rows,
            orientation=orientation,
            page_role=case.page_role,
            product_category=case.product_category,
            evidence_mode=evidence_mode,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    run = models.DisinfectionDecompositionRun(
        case_id=case.id,
        evidence_annotation_ids_json=json.dumps([row.id for row in few_shots]),
        model_name=config.VISION_MODEL or "",
        generation_mode="model",
        prompt_version="generic-layout-few-shot-v1",
    )
    db.add(run)
    db.flush()
    if len(few_shots) < 3:
        run.status = "review_required"
        run.failure_reasons_json = json.dumps(
            ["not_ready: at least 3 verified calibration annotations are required"],
            ensure_ascii=False,
        )
        db.commit()
        db.refresh(run)
        return _decomposition_run_dict(run)
    if not config.vlm_enabled():
        run.status = "review_required"
        run.failure_reasons_json = json.dumps(
            ["vision_model_unavailable; no fallback blueprint generated"],
            ensure_ascii=False,
        )
        db.commit()
        db.refresh(run)
        return _decomposition_run_dict(run)
    evidence = [
        {
            "annotation_id": row.id,
            "product_category": row.product_category,
            "source_type": row.source_type,
            "evidence_role": (
                "company_standard"
                if row.source_type == "company_published"
                and row.product_category == case.product_category
                else "cross_category_structure_reference"
                if row.source_type == "company_published"
                else "imitation_reference"
            ),
            "canvas_ratio": disinfection_annotations.canvas_ratio(
                row.canvas_width, row.canvas_height
            ),
            "orientation": row.orientation,
            "page_role": row.page_role,
            "regions": json.loads(row.regions_json or "[]"),
        }
        for row in few_shots
    ]
    try:
        result = run_pipeline(
            str(image_path),
            asset_category="layout",
            strict_vlm=True,
            layout_few_shots=evidence,
        )
        modules = result.layout.blueprint_modules or []
        if not modules:
            raise ValueError("model returned no blueprint modules")
        layout_blueprint.validate_modules(modules, len(modules))
        if not any(module["type"] == "product_image" for module in modules):
            raise ValueError("model did not identify product_image")
        payload = crud.build_initial_layout_blueprint(case.image, result)
        blueprint = crud.create_layout_blueprint(db, case.id, payload)
        snapshot = crud.serialize_layout_blueprint(blueprint)
        low_confidence = [
            module["id"] for module in modules
            if float(module.get("confidence", 1)) < 0.55
        ]
        run.blueprint_id = blueprint.id
        run.initial_ai_blueprint_json = json.dumps(snapshot, ensure_ascii=False, default=str)
        run.status = "review_required" if low_confidence else "ai_generated"
        run.failure_reasons_json = json.dumps(
            [f"low_confidence_modules:{','.join(low_confidence)}"] if low_confidence else [],
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        run.status = "review_required"
        run.failure_reasons_json = json.dumps(
            [f"model_failure:{type(exc).__name__}:{exc}"], ensure_ascii=False
        )
        run.blueprint_id = None
        run.initial_ai_blueprint_json = "{}"
    db.commit()
    db.refresh(run)
    return _decomposition_run_dict(run)


@app.get("/api/layout-annotations/evaluation")
@app.get("/api/disinfection-annotations/evaluation")
def evaluate_disinfection_holdout(
    product_category: str = "",
    db: Session = Depends(get_db),
) -> dict:
    annotations = (
        db.query(models.DisinfectionAnnotation)
        .filter(
            models.DisinfectionAnnotation.status == "verified",
            models.DisinfectionAnnotation.source_type == "company_published",
        )
        .all()
    )
    if product_category:
        annotations = [
            row for row in annotations if row.product_category == product_category
        ]
    holdout = [row for row in annotations if row.dataset_split == "holdout"]
    calibration = [row for row in annotations if row.dataset_split == "calibration"]
    runs = db.query(models.DisinfectionDecompositionRun).all()
    evaluated: list[dict] = []
    # Evaluation is only possible when a holdout annotation has an explicitly
    # paired original image and a traceable run for that case.
    for annotation in holdout:
        if not annotation.original_image_path:
            continue
        matching_case = _find_annotation_original_case(db, annotation)
        run = next(
            (
                candidate for candidate in reversed(runs)
                if matching_case and candidate.case_id == matching_case.id
                and candidate.initial_ai_blueprint_json not in ("", "{}")
            ),
            None,
        )
        if not run:
            continue
        predicted = json.loads(run.initial_ai_blueprint_json).get("modules_json", [])
        truth = json.loads(annotation.regions_json or "[]")
        evaluated.append({
            "annotation_id": annotation.id,
            **disinfection_annotations.evaluate_regions(predicted, truth),
            "manual_edit_count": run.manual_edit_count,
            "no_edit": run.manual_edit_count == 0,
        })
    if not calibration or not holdout or not evaluated:
        return {
            "status": "not_ready",
            "calibration_count": len(calibration),
            "holdout_count": len(holdout),
            "evaluated_count": len(evaluated),
            "metrics": {},
            "gates": {},
            "message": "Need verified project-grouped calibration and holdout annotations, paired unannotated originals, and traceable AI runs.",
        }
    def average(key: str) -> float:
        values = [row[key] for row in evaluated if row.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0
    metrics = {
        "product_image_iou": average("product_image_iou"),
        "main_text_iou": average("main_text_iou"),
        "layout_block_mean_iou": average("layout_block_mean_iou"),
        "product_image_accuracy": average("product_image_accuracy"),
        "main_text_accuracy": average("main_text_accuracy"),
        "module_type_accuracy": average("module_type_accuracy"),
        "missed": sum(row["missed"] for row in evaluated),
        "extra": sum(row["extra"] for row in evaluated),
        "out_of_bounds": sum(row["out_of_bounds"] for row in evaluated),
        "coordinate_validity": average("coordinate_validity"),
        "manual_edit_count": sum(row["manual_edit_count"] for row in evaluated),
        "no_edit_rate": round(sum(row["no_edit"] for row in evaluated) / len(evaluated), 4),
    }
    gates = {
        "evaluated_count_gte_5": len(evaluated) >= 5,
        "product_image_accuracy_gte_90": metrics["product_image_accuracy"] >= 0.90,
        "main_text_accuracy_gte_80": metrics["main_text_accuracy"] >= 0.80,
        "module_type_accuracy_gte_80": metrics["module_type_accuracy"] >= 0.80,
        "coordinates_legal_100": metrics["coordinate_validity"] == 1.0,
    }
    coverage_ready = gates["evaluated_count_gte_5"]
    return {
        "status": (
            "not_ready" if not coverage_ready
            else "passed" if all(gates.values())
            else "failed"
        ),
        "calibration_count": len(calibration),
        "holdout_count": len(holdout),
        "evaluated_count": len(evaluated),
        "metrics": metrics,
        "gates": gates,
        "items": evaluated,
        "message": (
            "" if coverage_ready
            else "At least 5 successful blind holdout runs are required before pass/fail."
        ),
        "holdout_policy": "Holdout is excluded from few-shot retrieval and must not be used for prompt iteration.",
    }


@app.on_event("startup")
def _startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        stale_jobs = (
            db.query(models.CategorySuggestionJob)
            .filter(models.CategorySuggestionJob.status.in_(["queued", "running"]))
            .all()
        )
        for job in stale_jobs:
            job.status = "interrupted"
            job.finished_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
            job.errors = json.dumps(
                [
                    {
                        "case_id": None,
                        "detail": "服务重启导致任务中断，请重新提交未完成素材",
                    }
                ],
                ensure_ascii=False,
            )
        batch.recover_stale_jobs(db)
        db.commit()
    finally:
        db.close()


@app.on_event("shutdown")
def _shutdown() -> None:
    close_db()


@app.get("/api/health")
def health() -> dict:
    vlm_on = config.vlm_enabled()
    return {
        "status": "ok",
        "vision_provider": config.VISION_PROVIDER,
        "vlm_enabled": vlm_on,
        "vision_missing_config": config.vision_missing_config(),
        "model": config.VISION_MODEL if vlm_on else "启发式规则",
        "llm_enabled": config.llm_enabled(),
        "llm_model": config.LLM_MODEL if config.llm_enabled() else "",
    }


def _require_admin(x_workbench_role: str = Header(default="designer")) -> str:
    """Temporary centralized role seam; replace with real auth when available."""
    if x_workbench_role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return x_workbench_role


@app.get("/api/admin/provider-availability")
def get_provider_availability(_: str = Depends(_require_admin)):
    return provider_workflow.workflow_status()


@app.post("/api/admin/provider-availability/run")
def run_provider_availability_stage(
    payload: ProviderWorkflowStageInput,
    _: str = Depends(_require_admin),
):
    try:
        return provider_workflow.start_stage(payload.stage)
    except provider_workflow.WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/analysis-evaluation/datasets")
def list_analysis_datasets(
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    rows = (
        db.query(models.AnalysisEvaluationDataset)
        .order_by(models.AnalysisEvaluationDataset.created_at.desc())
        .all()
    )
    return [analysis_evaluation.dataset_detail(db, row, admin=True) for row in rows]


@app.post("/api/analysis-evaluation/datasets")
def create_analysis_dataset(
    payload: AnalysisDatasetCreate,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        row = analysis_evaluation.create_dataset(db, payload.model_dump())
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return analysis_evaluation.dataset_detail(db, row, admin=True)


@app.get("/api/analysis-evaluation/datasets/{dataset_version}")
def get_analysis_dataset(
    dataset_version: str,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        row = analysis_evaluation.dataset_or_error(db, dataset_version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis_evaluation.dataset_detail(db, row, admin=True)


@app.post("/api/analysis-evaluation/datasets/{dataset_version}/items")
def assign_analysis_dataset_item(
    dataset_version: str,
    payload: AnalysisDatasetItemUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        dataset = analysis_evaluation.dataset_or_error(db, dataset_version)
        row = analysis_evaluation.assign_item(db, dataset, payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return analysis_evaluation.serialize_item(row, include_ground_truth=False)


@app.put("/api/analysis-evaluation/datasets/{dataset_version}/items/{item_id}/ground-truth")
def update_analysis_ground_truth(
    dataset_version: str,
    item_id: int,
    payload: AnalysisGroundTruthUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        dataset = analysis_evaluation.dataset_or_error(db, dataset_version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    item = db.get(models.AnalysisEvaluationItem, item_id)
    if not item or item.dataset_id != dataset.id:
        raise HTTPException(status_code=404, detail="数据集条目不存在")
    try:
        row = analysis_evaluation.save_ground_truth(
            db, dataset, item, payload.model_dump(mode="json")
        )
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return analysis_evaluation.serialize_item(row, include_ground_truth=True)


@app.get("/api/analysis-evaluation/public-summary")
def analysis_evaluation_public_summary(db: Session = Depends(get_db)):
    """Designer-safe endpoint: never returns holdout labels or ground truth."""
    rows = db.query(models.AnalysisEvaluationDataset).all()
    return [
        analysis_evaluation.dataset_detail(db, row, admin=False) for row in rows
    ]


@app.get("/api/analysis-versions")
def list_analysis_versions(
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    rows = (
        db.query(models.AnalysisRuntimeVersion)
        .order_by(models.AnalysisRuntimeVersion.created_at.desc())
        .all()
    )
    return [
        analysis_evaluation.runtime_to_dict(row, technical=True) for row in rows
    ]


@app.post("/api/analysis-versions")
def create_analysis_version(
    payload: AnalysisRuntimeVersionCreate,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        row = analysis_evaluation.create_runtime(db, payload.model_dump())
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return analysis_evaluation.runtime_to_dict(row, technical=True)


@app.post("/api/analysis-versions/freeze")
def freeze_analysis_version(
    payload: AnalysisVersionFreezeInput,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        dataset = analysis_evaluation.dataset_or_error(db, payload.dataset_version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    runtime = db.get(models.AnalysisRuntimeVersion, payload.runtime_version_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="运行版本不存在")
    try:
        analysis_evaluation.freeze_runtime(db, dataset, runtime)
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "dataset": analysis_evaluation.dataset_detail(db, dataset, admin=True),
        "runtime": analysis_evaluation.runtime_to_dict(runtime, technical=True),
    }


@app.post("/api/analysis-evaluation/runs")
def run_analysis_evaluation(
    payload: AnalysisEvaluationRunCreate,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    try:
        dataset = analysis_evaluation.dataset_or_error(db, payload.dataset_version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    runtime = db.get(models.AnalysisRuntimeVersion, payload.runtime_version_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="运行版本不存在")
    try:
        row = analysis_evaluation.run_evaluation(
            db,
            dataset,
            runtime,
            dataset_split=payload.dataset_split,
            actor=payload.created_by,
            confirm_holdout=payload.confirm_consume_holdout,
        )
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return analysis_evaluation.run_to_dict(
        row, include_details=payload.dataset_split == "calibration", db=db
    )


@app.get("/api/analysis-evaluation/runs")
def list_analysis_evaluation_runs(
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    rows = (
        db.query(models.AnalysisEvaluationRun)
        .order_by(models.AnalysisEvaluationRun.created_at.desc())
        .all()
    )
    return [
        analysis_evaluation.run_to_dict(
            row,
            include_details=row.dataset_split == "calibration" or bool(row.unsealed_at),
            db=db,
        )
        for row in rows
    ]


@app.get("/api/analysis-evaluation/runs/{run_id}")
def get_analysis_evaluation_run(
    run_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    row = db.get(models.AnalysisEvaluationRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return analysis_evaluation.run_to_dict(
        row,
        include_details=row.dataset_split == "calibration" or bool(row.unsealed_at),
        db=db,
    )


@app.post("/api/analysis-evaluation/runs/{run_id}/unseal")
def unseal_analysis_evaluation_run(
    run_id: int,
    payload: AnalysisHoldoutUnsealInput,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    if not payload.confirm_consumed:
        raise HTTPException(
            status_code=409,
            detail="必须确认解封后当前 Holdout 将标记为 consumed",
        )
    row = db.get(models.AnalysisEvaluationRun, run_id)
    if not row or row.dataset_split != "holdout":
        raise HTTPException(status_code=404, detail="Holdout 运行记录不存在")
    dataset = db.get(models.AnalysisEvaluationDataset, row.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")
    now = dt.datetime.utcnow()
    row.unsealed_at = now
    analysis_evaluation.mark_consumed(dataset, now=now)
    db.commit()
    return analysis_evaluation.run_to_dict(row, include_details=True, db=db)


@app.post("/api/analysis-evaluation/results/{result_id}/retry")
def retry_analysis_evaluation_result(
    result_id: int,
    payload: AnalysisResultRetryInput,
    db: Session = Depends(get_db),
    _: str = Depends(_require_admin),
):
    result = db.get(models.AnalysisEvaluationResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="拆解结果不存在")
    run = db.get(models.AnalysisEvaluationRun, result.run_id)
    if not run or run.dataset_split != "calibration":
        raise HTTPException(status_code=409, detail="仅 Calibration 失败项允许单条重试")
    try:
        return analysis_evaluation.retry_result(db, result, actor=payload.actor)
    except analysis_evaluation.EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=CaseOut)
async def analyze_image(
    file: UploadFile = File(...),
    uploader: str = Form("anonymous"),
    source_type: str = Form("external_reference"),
    source_url: str = Form(""),
    rights_note: str = Form(""),
    product_category: str = Form(""),
    asset_category: str = Form("layout"),
    asset_subcategory: str = Form(""),
    db: Session = Depends(get_db),
):
    """上传图片 → 运行 AI Agent 流水线 → 生成并保存案例卡。

    覆盖技术方案 MVP 核心功能：图片上传 / AI视觉分析 / 自动生成案例卡。
    """
    try:
        source_type = normalize_new_source_type(source_type, "external_reference")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    ext = Path(file.filename or "").suffix or ".png"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = config.UPLOAD_DIR / stored_name
    dest.write_bytes(await file.read())

    # 感知哈希去重：近重复直接返回已有案例，省去重复拆解
    phash = ""
    try:
        phash = imagehash.dhash(str(dest))
        dup_id = crud.find_duplicate_case_id(
            db, phash, asset_category=asset_category
        )
        if dup_id:
            dest.unlink(missing_ok=True)
            dup = db.query(models.Case).filter(models.Case.id == dup_id).first()
            if dup:
                return crud.serialize_case(dup)
    except Exception:
        pass

    image = models.Image(
        url=f"/uploads/{stored_name}",
        filename=file.filename or stored_name,
        source="upload",
        source_type=source_type,
        source_url=source_url,
        rights_note=rights_note,
        visibility="team",
        uploader=uploader,
        phash=phash,
    )
    db.add(image)
    db.flush()

    try:
        result = run_pipeline(str(dest), asset_category=asset_category)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"分析失败：{exc}") from exc

    case = crud.create_case_from_analysis(
        db,
        image,
        result,
        product_category=product_category,
        asset_category=asset_category,
        asset_subcategory=asset_subcategory,
    )
    return crud.serialize_case(case)


@app.post("/api/analyze/batch")
async def analyze_batch(
    files: list[UploadFile] = File(...),
    uploader: str = Form("anonymous"),
    source_type: str = Form("external_reference"),
    source_url: str = Form(""),
    rights_note: str = Form(""),
    product_category: str = Form(""),
    asset_category: str = Form("layout"),
    asset_subcategory: str = Form(""),
):
    """批量上传：先落盘，起后台任务顺序拆解入库，返回 batch_id 供轮询进度。"""
    try:
        source_type = normalize_new_source_type(source_type, "external_reference")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = []
    for f in files:
        if not (f.content_type or "").startswith("image/"):
            continue
        ext = Path(f.filename or "").suffix or ".png"
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = config.UPLOAD_DIR / stored_name
        dest.write_bytes(await f.read())
        items.append(
            {
                "path": str(dest),
                "url": f"/uploads/{stored_name}",
                "filename": f.filename or stored_name,
                "uploader": uploader,
                "source_type": source_type,
                "source_url": source_url,
                "rights_note": rights_note,
                "product_category": product_category,
                "asset_category": asset_category,
                "asset_subcategory": asset_subcategory,
            }
        )
    if not items:
        raise HTTPException(status_code=400, detail="没有有效的图片文件")
    batch_id = batch.create_batch(items)
    return {"batch_id": batch_id, "total": len(items)}


@app.get("/api/analyze/batch/{batch_id}")
def analyze_batch_status(batch_id: str):
    """查询批量拆解进度。"""
    b = batch.get_batch(batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"batch_id": batch_id, **b}


@app.get("/api/cases", response_model=list[CaseOut])
def list_cases(
    q: str | None = None,
    tag: str | None = None,
    asset_category: str | None = None,
    asset_subcategory: str | None = None,
    project_id: int | None = None,
    trust_status: str | None = None,
    analysis_mode: str | None = None,
    product_name: str | None = None,
    content_purpose: str | None = None,
    page_role: str | None = None,
    db: Session = Depends(get_db),
):
    """案例资产库：支持关键词搜索与标签检索。"""
    cases = crud.search_cases(
        db,
        q=q,
        tag=tag,
        asset_category=asset_category,
        asset_subcategory=asset_subcategory,
        project_id=project_id,
        trust_status=trust_status,
        analysis_mode=analysis_mode,
        product_name=product_name,
        content_purpose=content_purpose,
        page_role=page_role,
    )
    return [crud.serialize_case(c) for c in cases]


@app.get("/api/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    return crud.serialize_case(case)


@app.patch("/api/cases/{case_id}/business", response_model=CaseOut)
def update_case_business(
    case_id: int,
    payload: CaseBusinessUpdate,
    db: Session = Depends(get_db),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    return crud.serialize_case(crud.update_case_business_fields(db, case, payload))


@app.get(
    "/api/cases/{case_id}/layout-blueprints",
    response_model=list[LayoutBlueprintOut],
)
def list_case_layout_blueprints(
    case_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.Case, case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return [
        crud.serialize_layout_blueprint(item)
        for item in crud.list_layout_blueprints(db, case_id)
    ]


@app.post(
    "/api/cases/{case_id}/layout-blueprints/generate",
    response_model=LayoutBlueprintOut,
)
def generate_case_layout_blueprint(
    case_id: int,
    db: Session = Depends(get_db),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    try:
        payload = crud.build_layout_blueprint_for_case(case)
        blueprint = crud.create_layout_blueprint(db, case.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_layout_blueprint(blueprint)


@app.get(
    "/api/layout-blueprints/{blueprint_id}",
    response_model=LayoutBlueprintOut,
)
def get_layout_blueprint(
    blueprint_id: int,
    db: Session = Depends(get_db),
):
    blueprint = crud.get_layout_blueprint(db, blueprint_id)
    if not blueprint:
        raise HTTPException(status_code=404, detail="排版骨架不存在")
    return crud.serialize_layout_blueprint(blueprint)


@app.post(
    "/api/layout-blueprints/{blueprint_id}/revise",
    response_model=LayoutBlueprintOut,
)
def revise_layout_blueprint(
    blueprint_id: int,
    payload: LayoutBlueprintInput,
    db: Session = Depends(get_db),
):
    try:
        human_payload = LayoutBlueprintInput.model_validate(
            {
                **payload.model_dump(),
                "review_status": "human_edited",
            }
        )
        blueprint = crud.revise_layout_blueprint(
            db,
            blueprint_id,
            human_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_layout_blueprint(blueprint)


@app.post(
    "/api/layout-blueprints/{blueprint_id}/verify",
    response_model=LayoutBlueprintOut,
)
def verify_layout_blueprint(
    blueprint_id: int,
    payload: LayoutBlueprintVerifyInput,
    db: Session = Depends(get_db),
):
    current = crud.get_layout_blueprint(db, blueprint_id)
    if not current:
        raise HTTPException(status_code=404, detail="排版骨架不存在")
    current_data = crud.serialize_layout_blueprint(current)
    verified_payload = LayoutBlueprintInput.model_validate(
        {
            **current_data,
            "review_status": "verified",
            "editor": payload.editor,
        }
    )
    verified = crud.revise_layout_blueprint(
        db,
        current.id,
        verified_payload,
    )
    return crud.serialize_layout_blueprint(verified)


@app.get(
    "/api/cases/{case_id}/layout-blueprint",
    response_model=LayoutBlueprintOut,
)
def get_current_case_layout_blueprint(
    case_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.Case, case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    blueprint = crud.get_latest_layout_blueprint(db, case_id)
    if not blueprint:
        raise HTTPException(status_code=404, detail="排版蓝图不存在")
    return crud.serialize_layout_blueprint(blueprint)


@app.get(
    "/api/cases/{case_id}/layout-blueprint/versions",
    response_model=list[LayoutBlueprintOut],
)
def get_case_layout_blueprint_versions(
    case_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.Case, case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return [
        crud.serialize_layout_blueprint(item)
        for item in crud.list_layout_blueprints(db, case_id)
    ]


@app.patch(
    "/api/cases/{case_id}/layout-blueprint",
    response_model=LayoutBlueprintOut,
)
def patch_case_layout_blueprint(
    case_id: int,
    payload: LayoutBlueprintInput,
    expected_version: int | None = None,
    db: Session = Depends(get_db),
):
    if not db.get(models.Case, case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    current = crud.get_latest_layout_blueprint(db, case_id)
    if not current:
        raise HTTPException(status_code=404, detail="排版蓝图不存在")
    if expected_version is not None and current.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"版本冲突：当前为 v{current.version}，提交基于 v{expected_version}",
        )
    corrected = LayoutBlueprintInput.model_validate(
        {
            **payload.model_dump(),
            "review_status": "corrected",
        }
    )
    return crud.serialize_layout_blueprint(
        crud.create_layout_blueprint(db, case_id, corrected)
    )


@app.post(
    "/api/cases/{case_id}/layout-blueprint/regenerate",
    response_model=LayoutBlueprintOut,
)
def regenerate_case_layout_blueprint_v2(
    case_id: int,
    db: Session = Depends(get_db),
):
    case = db.get(models.Case, case_id)
    if not case or not case.image:
        raise HTTPException(status_code=404, detail="案例或原始图片不存在")
    image_path = config.UPLOAD_DIR / Path(case.image.url).name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="原始图片文件不存在")
    try:
        result = run_pipeline(str(image_path), asset_category="layout")
        payload = crud.build_initial_layout_blueprint(case.image, result)
        blueprint = crud.create_layout_blueprint(db, case_id, payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI重新拆解失败：{exc}") from exc
    return crud.serialize_layout_blueprint(blueprint)


@app.post(
    "/api/cases/{case_id}/layout-blueprint/verify",
    response_model=LayoutBlueprintOut,
)
def verify_case_layout_blueprint_v2(
    case_id: int,
    payload: LayoutBlueprintVerifyInput,
    db: Session = Depends(get_db),
):
    if not db.get(models.Case, case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    current = crud.get_latest_layout_blueprint(db, case_id)
    if not current:
        raise HTTPException(status_code=404, detail="排版蓝图不存在")
    if payload.version is not None and current.version != payload.version:
        raise HTTPException(status_code=409, detail="只能确认当前版本，版本已发生变化")
    if current.review_status == "verified":
        raise HTTPException(status_code=409, detail="当前版本已经确认")
    verified_payload = LayoutBlueprintInput.model_validate(
        {
            **crud.serialize_layout_blueprint(current),
            "review_status": "verified",
            "editor": payload.editor,
        }
    )
    return crud.serialize_layout_blueprint(
        crud.create_layout_blueprint(db, case_id, verified_payload)
    )


@app.get("/api/layout-patterns", response_model=list[LayoutPatternOut])
def list_layout_patterns(
    orientation: str = "",
    canvas_ratio: str = "",
    information_density: str = "",
    confidence_level: str = "",
    scene: str = "",
    channel: str = "",
    review_status: str = "",
    db: Session = Depends(get_db),
):
    items = [
        crud.serialize_layout_pattern(item)
        for item in crud.list_layout_patterns(
            db,
            orientation=orientation,
            scene=scene,
            channel=channel,
            review_status=review_status,
        )
    ]
    if canvas_ratio:
        items = [item for item in items if item["canvas_ratio"] == canvas_ratio]
    if information_density:
        items = [item for item in items if item["information_density"] == information_density]
    if confidence_level:
        items = [item for item in items if item["confidence_level"] == confidence_level]
    return items


@app.post("/api/layout-patterns", response_model=LayoutPatternOut)
def create_layout_pattern(
    payload: LayoutPatternCreate,
    db: Session = Depends(get_db),
):
    try:
        pattern = crud.create_layout_pattern(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_layout_pattern(pattern)


@app.post("/api/layout-patterns/rebuild")
def rebuild_layout_patterns(
    payload: LayoutPatternRebuildInput,
    db: Session = Depends(get_db),
):
    try:
        return layout_patterns.rebuild(
            db,
            dry_run=payload.dry_run,
            similarity_threshold=payload.similarity_threshold,
            minimum_evidence=payload.minimum_evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/layout-patterns/{pattern_id}", response_model=LayoutPatternOut)
def get_layout_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
):
    pattern = db.get(models.LayoutPattern, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="排版模式不存在")
    return crud.serialize_layout_pattern(pattern)


@app.patch("/api/layout-patterns/{pattern_id}", response_model=LayoutPatternOut)
def patch_layout_pattern(
    pattern_id: int,
    payload: LayoutPatternPatch,
    db: Session = Depends(get_db),
):
    pattern = db.get(models.LayoutPattern, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="排版模式不存在")
    if pattern.review_status == "disabled":
        raise HTTPException(status_code=409, detail="已停用模式不能编辑")
    values = payload.model_dump(exclude_none=True)
    for key in (
        "module_structure_json", "suitable_scenes_json",
        "unsuitable_scenes_json", "product_category_tags_json",
        "content_purpose_tags_json", "campaign_stage_tags_json",
    ):
        if key in values:
            setattr(pattern, key, json.dumps(values.pop(key), ensure_ascii=False))
    for key, value in values.items():
        setattr(pattern, key, value)
    if pattern.discovery_method == layout_patterns.DISCOVERY_METHOD:
        pattern.discovery_method = "manual-edited"
    if pattern.business_context_review_status == "verified":
        pattern.business_context_reviewer = payload.reviewer
    db.commit()
    db.refresh(pattern)
    return crud.serialize_layout_pattern(pattern)


@app.post(
    "/api/layout-patterns/{pattern_id}/revise",
    response_model=LayoutPatternOut,
)
def revise_layout_pattern(
    pattern_id: int,
    payload: LayoutPatternUpdate,
    db: Session = Depends(get_db),
):
    if not db.get(models.LayoutPattern, pattern_id):
        raise HTTPException(status_code=404, detail="排版模式不存在")
    try:
        pattern = crud.create_layout_pattern(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_layout_pattern(pattern)


@app.post(
    "/api/layout-patterns/{pattern_id}/verify",
    response_model=LayoutPatternOut,
)
def verify_layout_pattern(
    pattern_id: int,
    payload: LayoutPatternVerifyInput,
    db: Session = Depends(get_db),
):
    current = db.get(models.LayoutPattern, pattern_id)
    if not current:
        raise HTTPException(status_code=404, detail="排版模式不存在")
    if current.review_status == "disabled":
        raise HTTPException(status_code=409, detail="已停用模式不能确认")
    if current.review_status == "verified":
        raise HTTPException(status_code=409, detail="模式已经确认")
    serialized = crud.serialize_layout_pattern(current)
    evidence_case_ids = set(serialized["evidence_case_ids_json"])
    representative_ids = set(payload.representative_case_ids)
    missing_requirements = []
    if len(evidence_case_ids) < 3:
        missing_requirements.append("至少3个不同公司案例")
    if not representative_ids or not representative_ids.issubset(evidence_case_ids):
        missing_requirements.append("代表案例明确且属于模式证据")
    if not current.name.strip() or not payload.name_confirmed:
        missing_requirements.append("模式名称已确认")
    if (
        not payload.scenes_confirmed
        or not crud._json_list(current.suitable_scenes_json)
        or not crud._json_list(current.unsuitable_scenes_json)
    ):
        missing_requirements.append("适用和不适用场景已确认")
    if not payload.modules_confirmed or not crud._json_list(current.required_modules_json):
        missing_requirements.append("必需模块和可选模块已确认")
    if not payload.design_owner_confirmed:
        missing_requirements.append("设计负责人确认")
    if missing_requirements:
        raise HTTPException(status_code=422, detail={"missing_requirements": missing_requirements})
    if current.pattern_code:
        current.review_status = "verified"
        current.reviewer = payload.editor
        current.editor = payload.editor
        db.commit()
        db.refresh(current)
        return crud.serialize_layout_pattern(current)
    data = crud.serialize_layout_pattern(current)
    verified_payload = LayoutPatternUpdate.model_validate(
        {
            "name": data["name"],
            "description": data["description"],
            "source_blueprint_ids": data["source_blueprint_ids"],
            "industry_tags": data["industry_tags"],
            "scene_tags": data["scene_tags"],
            "channel_tags": data["channel_tags"],
            "business_goal_tags": data["business_goal_tags"],
            "usage_notes": data["usage_notes"],
            "editor": payload.editor,
            "review_status": "verified",
        }
    )
    try:
        verified = crud.create_layout_pattern(db, verified_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_layout_pattern(verified)


@app.post("/api/layout-patterns/{pattern_id}/disable", response_model=LayoutPatternOut)
def disable_layout_pattern(
    pattern_id: int,
    payload: LayoutBlueprintVerifyInput,
    db: Session = Depends(get_db),
):
    pattern = db.get(models.LayoutPattern, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="排版模式不存在")
    if pattern.review_status == "disabled":
        raise HTTPException(status_code=409, detail="模式已经停用")
    pattern.review_status = "disabled"
    pattern.reviewer = payload.editor
    db.commit()
    db.refresh(pattern)
    return crud.serialize_layout_pattern(pattern)


@app.get("/api/layout-patterns/{pattern_id}/evidence")
def get_layout_pattern_evidence(
    pattern_id: int,
    db: Session = Depends(get_db),
):
    pattern = db.get(models.LayoutPattern, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="排版模式不存在")
    report = layout_patterns.evidence_report(db, pattern)
    return {
        "cases": [crud.serialize_case(item) for item in report["cases"]],
        "blueprints": [
            crud.serialize_layout_blueprint(item)
            for item in report["blueprints"]
        ],
        "similarities": report["similarities"],
        "participating_modules": report["participating_modules"],
        "excluded_modules": report["excluded_modules"],
        "evidence_count": report["evidence_count"],
    }


@app.get(
    "/api/business-requirements",
    response_model=list[BusinessRequirementOut],
)
def list_business_requirements(
    status: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(models.BusinessRequirement)
    if status:
        query = query.filter(models.BusinessRequirement.status == status)
    return [
        crud.serialize_business_requirement(item)
        for item in query.order_by(
            models.BusinessRequirement.updated_at.desc(),
            models.BusinessRequirement.id.desc(),
        ).all()
    ]


@app.post("/api/business-requirements/reference-image")
async def upload_business_requirement_reference_image(
    file: UploadFile = File(...),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="参考文件必须是图片")
    ext = Path(file.filename or "").suffix or ".png"
    stored_name = f"requirement-{uuid.uuid4().hex}{ext}"
    destination = config.UPLOAD_DIR / stored_name
    destination.write_bytes(await file.read())
    return {"path": f"/uploads/{stored_name}"}


@app.post(
    "/api/business-requirements",
    response_model=BusinessRequirementOut,
)
def create_business_requirement(
    payload: BusinessRequirementCreate,
    db: Session = Depends(get_db),
):
    try:
        requirement = crud.create_business_requirement(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_business_requirement(requirement)


@app.get(
    "/api/business-requirements/{requirement_id}",
    response_model=BusinessRequirementOut,
)
def get_business_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    return crud.serialize_business_requirement(requirement)


@app.patch(
    "/api/business-requirements/{requirement_id}",
    response_model=BusinessRequirementOut,
)
def patch_business_requirement(
    requirement_id: int,
    payload: BusinessRequirementUpdate,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    try:
        updated = crud.update_business_requirement(db, requirement, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_business_requirement(updated)


@app.post(
    "/api/business-requirements/{requirement_id}/confirm",
    response_model=BusinessRequirementOut,
)
def confirm_business_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    if requirement.status == "archived":
        raise HTTPException(status_code=409, detail="已归档需求不能确认")
    requirement.status = "confirmed"
    db.commit()
    db.refresh(requirement)
    return crud.serialize_business_requirement(requirement)


@app.post(
    "/api/business-requirements/{requirement_id}/match",
    response_model=BusinessRequirementMatchOut,
    deprecated=True,
)
def match_business_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    return crud.match_business_requirement(db, requirement)


@app.post("/api/business-requirements/{requirement_id}/layout-search")
def search_requirement_layouts(
    requirement_id: int,
    payload: LayoutSearchInput,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    return layout_search.run_search(
        db,
        requirement,
        pattern_limit=payload.pattern_limit,
        case_limit=payload.case_limit,
        include_unverified=payload.include_unverified,
        reanalyze_reference=payload.reanalyze_reference,
    )


@app.get("/api/business-requirements/{requirement_id}/layout-search/latest")
def latest_requirement_layout_search(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    result = layout_search.latest_search(db, requirement)
    if not result:
        raise HTTPException(status_code=404, detail="该需求尚无检索记录")
    return result


@app.post("/api/layout-search-runs/{run_id}/feedback")
def create_layout_search_feedback(
    run_id: int,
    payload: LayoutSearchFeedbackCreate,
    db: Session = Depends(get_db),
):
    run = db.get(models.LayoutSearchRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="检索运行不存在")
    try:
        row = layout_search.add_feedback(
            db,
            run,
            result_type=payload.result_type,
            result_id=payload.result_id,
            rank=payload.rank,
            relevance=payload.relevance,
            reviewer=payload.reviewer,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": row.id,
        "search_run_id": row.search_run_id,
        "requirement_id": row.requirement_id,
        "result_type": row.result_type,
        "result_id": row.result_id,
        "rank": row.rank,
        "relevance": row.relevance,
        "reviewer": row.reviewer,
        "notes": row.notes,
        "created_at": row.created_at,
    }


@app.get("/api/layout-search/ground-truth")
def get_layout_search_ground_truth(
    dataset_version: str | None = None, db: Session = Depends(get_db),
):
    return layout_search.list_ground_truth(db, dataset_version)


@app.get("/api/layout-search/datasets")
def get_layout_search_datasets(db: Session = Depends(get_db)):
    return layout_search.list_datasets(db)


@app.post("/api/layout-search/datasets")
def create_layout_search_dataset(
    payload: LayoutSearchDatasetCreate, db: Session = Depends(get_db),
):
    try:
        return layout_search.create_dataset(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/layout-search/datasets/{dataset_version}")
def get_layout_search_dataset(
    dataset_version: str, db: Session = Depends(get_db),
):
    dataset = db.query(models.LayoutSearchDataset).filter(
        models.LayoutSearchDataset.dataset_version == dataset_version
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集版本不存在")
    return {
        **layout_search._dataset_dict(db, dataset),
        "ground_truth": layout_search.list_ground_truth(db, dataset_version),
        "evaluation": layout_search.evaluation(db, dataset_version),
    }


@app.post("/api/layout-search/ground-truth")
def create_layout_search_ground_truth(
    payload: LayoutSearchGroundTruthCreate, db: Session = Depends(get_db),
):
    try:
        return layout_search.create_ground_truth(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/layout-search/ground-truth/freeze")
def freeze_layout_search_ground_truth(
    payload: LayoutSearchGroundTruthFreeze, db: Session = Depends(get_db),
):
    try:
        return layout_search.freeze_ground_truth(db, payload.dataset_version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/layout-search/ground-truth/{ground_truth_id}")
def update_layout_search_ground_truth(
    ground_truth_id: int, payload: LayoutSearchGroundTruthUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(models.LayoutSearchGroundTruth, ground_truth_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ground Truth 不存在")
    try:
        return layout_search.update_ground_truth(db, row, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/layout-search/ground-truth/{ground_truth_id}")
def delete_layout_search_ground_truth(
    ground_truth_id: int, db: Session = Depends(get_db),
):
    row = db.get(models.LayoutSearchGroundTruth, ground_truth_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ground Truth 不存在")
    try:
        layout_search.delete_ground_truth(db, row)
        return {"deleted": True, "id": ground_truth_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/layout-search/evaluation")
def get_layout_search_evaluation(
    dataset_version: str | None = None, db: Session = Depends(get_db),
):
    return layout_search.evaluation(db, dataset_version)


@app.get("/api/layout-search/evaluation/requirements/{requirement_id}")
def get_requirement_layout_search_evaluation(
    requirement_id: int, dataset_version: str | None = None,
    db: Session = Depends(get_db),
):
    report = layout_search.evaluation(db, dataset_version)
    rows = [
        row for row in report["overall"]["requirements"]
        if row["requirement_id"] == requirement_id
    ]
    if not rows:
        raise HTTPException(status_code=404, detail="该需求没有验收数据")
    return {**report, "overall": {**report["overall"], "requirements": rows}}


@app.post("/api/layout-search/evaluation/run")
def run_layout_search_evaluation(
    payload: LayoutSearchEvaluationRunInput, db: Session = Depends(get_db),
):
    try:
        return layout_search.run_acceptance(
            db, payload.dataset_version, payload.dataset_split
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/layout-search/evaluation/export")
def export_layout_search_evaluation(
    dataset_version: str | None = None, db: Session = Depends(get_db),
):
    if not dataset_version:
        raise HTTPException(status_code=400, detail="必须指定 dataset_version")
    try:
        return acceptance_pack.export_pack(db, dataset_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/layout-search/evaluation/import")
async def import_layout_search_evaluation(
    file: UploadFile = File(...), execute: bool = False,
    db: Session = Depends(get_db),
):
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
        return acceptance_pack.import_pack(db, payload, execute=execute)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="验收 JSON 无法解析") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/business-requirements/{requirement_id}/directions",
    response_model=list[LayoutDirectionOut],
)
def list_requirement_directions(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.BusinessRequirement, requirement_id):
        raise HTTPException(status_code=404, detail="业务需求不存在")
    return [
        crud.serialize_layout_direction(item)
        for item in db.query(models.LayoutDirection)
        .filter(models.LayoutDirection.requirement_id == requirement_id)
        .order_by(
            models.LayoutDirection.generation_version.desc(),
            models.LayoutDirection.id,
        )
        .all()
    ]


@app.post(
    "/api/business-requirements/{requirement_id}/directions/generate",
    response_model=LayoutDirectionSetOut,
)
def generate_requirement_directions(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    if not config.ENABLE_LAYOUT_DIRECTIONS:
        raise HTTPException(
            status_code=403,
            detail="多案例排版方向尚未启用；真实业务验收通过后才能进入 Task 5",
        )
    requirement = db.get(models.BusinessRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="业务需求不存在")
    try:
        return crud.generate_layout_directions(db, requirement)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/layout-directions/{direction_id}/feedback",
    response_model=list[LayoutDirectionFeedbackOut],
)
def list_layout_direction_feedback(
    direction_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.LayoutDirection, direction_id):
        raise HTTPException(status_code=404, detail="排版方向不存在")
    return [
        crud.serialize_layout_direction_feedback(item)
        for item in db.query(models.LayoutDirectionFeedback)
        .filter(models.LayoutDirectionFeedback.direction_id == direction_id)
        .order_by(models.LayoutDirectionFeedback.created_at, models.LayoutDirectionFeedback.id)
        .all()
    ]


@app.post(
    "/api/layout-directions/{direction_id}/feedback",
    response_model=LayoutDirectionFeedbackOut,
)
def create_layout_direction_feedback(
    direction_id: int,
    payload: LayoutDirectionFeedbackCreate,
    db: Session = Depends(get_db),
):
    direction = db.get(models.LayoutDirection, direction_id)
    if not direction:
        raise HTTPException(status_code=404, detail="排版方向不存在")
    feedback = crud.create_layout_direction_feedback(db, direction, payload)
    return crud.serialize_layout_direction_feedback(feedback)


@app.patch("/api/cases/{case_id}/review", response_model=CaseOut)
def review_case(
    case_id: int,
    review: CaseReviewInput,
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    if not review.reviewer.strip():
        raise HTTPException(status_code=400, detail="校验人不能为空")
    try:
        case = crud.review_case(db, case, review)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return crud.serialize_case(case)


@app.post("/api/cases/{case_id}/confirm", response_model=CaseOut)
def confirm_case(
    case_id: int,
    review: CaseReviewInput,
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    confirmed = review.model_copy(update={"trust_status": "verified"})
    return crud.serialize_case(crud.review_case(db, case, confirmed))


@app.post("/api/cases/{case_id}/recommend", response_model=CaseOut)
def recommend_case(
    case_id: int,
    review: CaseReviewInput,
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    recommended = review.model_copy(update={"trust_status": "company_recommended"})
    return crud.serialize_case(crud.review_case(db, case, recommended))


@app.post("/api/training/batch-review")
def batch_review_cases(
    payload: BatchReviewInput,
    db: Session = Depends(get_db),
):
    """Review a curated queue in one operation while preserving one audit record per case."""
    reviewer = payload.reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=400, detail="审核人不能为空")
    case_ids = list(dict.fromkeys(payload.case_ids))
    if not case_ids or len(case_ids) > 100:
        raise HTTPException(status_code=400, detail="每次请选择 1～100 个案例")
    cases = (
        db.query(models.Case)
        .filter(models.Case.id.in_(case_ids))
        .order_by(models.Case.id)
        .all()
    )
    found = {case.id for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in found]
    trust_status = {
        "confirm": "verified",
        "recommend": "company_recommended",
        "reject": "rejected",
    }[payload.action]
    decision = "reject" if payload.action == "reject" else "adopt"
    updated: list[int] = []
    failed: list[dict] = []
    for case in cases:
        review = CaseReviewInput(
            reviewer=reviewer,
            trust_status=trust_status,
            review_decision=decision,
            review_notes=payload.review_notes,
            keep_reasons=payload.keep_reasons,
            avoid_reasons=payload.avoid_reasons,
            business_line=payload.business_line or case.business_line,
            channel=case.channel,
            campaign_stage=case.campaign_stage,
            business_goal=case.business_goal,
        )
        try:
            crud.review_case(db, case, review)
            updated.append(case.id)
        except ValueError as exc:
            failed.append({"case_id": case.id, "detail": str(exc)})
    return {
        "action": payload.action,
        "updated": updated,
        "updated_count": len(updated),
        "missing": missing,
        "failed": failed,
    }


@app.post("/api/training/batch-categorize")
def batch_categorize_cases(
    payload: BatchCategorizeInput,
    db: Session = Depends(get_db),
):
    """Classify selected company assets while preserving an audit entry."""
    actor = payload.actor.strip()
    if not actor:
        raise HTTPException(status_code=400, detail="归类操作人不能为空")
    case_ids = list(dict.fromkeys(payload.case_ids))
    if not case_ids or len(case_ids) > 100:
        raise HTTPException(status_code=400, detail="每次请选择 1～100 个案例")
    cases = (
        db.query(models.Case)
        .filter(models.Case.id.in_(case_ids))
        .order_by(models.Case.id)
        .all()
    )
    updated = []
    for case in cases:
        previous = case.asset_category or "layout"
        case.asset_category = payload.asset_category
        pending_suggestions = (
            db.query(models.AssetCategorySuggestion)
            .filter(
                models.AssetCategorySuggestion.case_id == case.id,
                models.AssetCategorySuggestion.status == "pending",
            )
            .all()
        )
        for suggestion in pending_suggestions:
            suggestion.status = (
                "accepted"
                if suggestion.suggested_category == payload.asset_category
                else "overridden"
            )
            suggestion.reviewer = actor
            suggestion.reviewed_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        db.add(
            models.CaseReview(
                case_id=case.id,
                project_id=case.project_id,
                reviewer=actor,
                action="categorize",
                trust_status=case.trust_status,
                decision=case.review_decision,
                notes=f"素材类别：{previous} → {payload.asset_category}",
                corrected_payload=json.dumps(
                    {
                        "asset_category": payload.asset_category,
                        "previous_asset_category": previous,
                    },
                    ensure_ascii=False,
                ),
                analysis_version=case.analysis.version if case.analysis else 0,
            )
        )
        updated.append(case.id)
    db.commit()
    return {
        "asset_category": payload.asset_category,
        "updated": updated,
        "updated_count": len(updated),
    }


def _serialize_category_suggestion(
    suggestion: models.AssetCategorySuggestion,
) -> dict:
    try:
        signals = json.loads(suggestion.signals or "[]")
    except Exception:
        signals = []
    return {
        "id": suggestion.id,
        "case_id": suggestion.case_id,
        "suggested_category": suggestion.suggested_category,
        "confidence": suggestion.confidence,
        "reason": suggestion.reason,
        "signals": signals,
        "model_name": suggestion.model_name,
        "status": suggestion.status,
        "reviewer": suggestion.reviewer,
        "created_at": suggestion.created_at,
    }


@app.get("/api/training/category-suggestions")
def list_category_suggestions(
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.AssetCategorySuggestion).join(
        models.Case,
        models.Case.id == models.AssetCategorySuggestion.case_id,
    )
    if project_id is not None:
        query = query.filter(models.Case.project_id == project_id)
    rows = query.order_by(models.AssetCategorySuggestion.id.desc()).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.case_id, row)
    return [_serialize_category_suggestion(row) for row in latest.values()]


@app.get("/api/training/category-discovery")
def category_discovery(db: Session = Depends(get_db)):
    """Group latest model suggestions into human-reviewable coverage candidates."""
    cases = (
        db.query(models.Case)
        .join(models.Image, models.Case.image_id == models.Image.id)
        .filter(models.Image.source_type == "company_published")
        .all()
    )
    case_map = {case.id: case for case in cases}
    rows = (
        db.query(models.AssetCategorySuggestion)
        .filter(models.AssetCategorySuggestion.case_id.in_(case_map))
        .order_by(models.AssetCategorySuggestion.id.desc())
        .all()
        if case_map
        else []
    )
    latest = {}
    for row in rows:
        latest.setdefault(row.case_id, row)

    category_names = {
        "layout": "排版",
        "style": "风格",
        "color": "色彩",
        "photo": "实拍图",
    }
    lines = sorted(
        {
            (case.business_line or "").strip()
            for case in cases
            if (case.business_line or "").strip()
        }
    )
    result = []
    for line in lines:
        line_cases = [
            case for case in cases if (case.business_line or "").strip() == line
        ]
        coverage = {
            category: sum(
                1 for case in line_cases if case.asset_category == category
            )
            for category in category_names
        }
        candidates = {category: [] for category in category_names}
        for case in line_cases:
            suggestion = latest.get(case.id)
            if not suggestion:
                continue
            candidates[suggestion.suggested_category].append(
                {
                    "case_id": case.id,
                    "case_name": case.name,
                    "image_url": case.image.url if case.image else "",
                    "current_category": case.asset_category,
                    "suggested_category": suggestion.suggested_category,
                    "confidence": suggestion.confidence,
                    "reason": suggestion.reason,
                    "signals": json.loads(suggestion.signals or "[]"),
                    "status": suggestion.status,
                }
            )
        for items in candidates.values():
            items.sort(key=lambda item: (-item["confidence"], item["case_id"]))
        gaps = [
            {
                "category": category,
                "label": category_names[category],
                "needed": max(0, 2 - coverage[category]),
                "candidate_count": len(candidates[category]),
            }
            for category in category_names
            if coverage[category] < 2
        ]
        result.append(
            {
                "business_line": line,
                "coverage": coverage,
                "gaps": gaps,
                "candidates": candidates,
                "suggested_count": sum(len(items) for items in candidates.values()),
                "total_assets": len(line_cases),
            }
        )
    return result


@app.post("/api/training/batch-suggest-categories")
def batch_suggest_categories(
    payload: BatchCategorySuggestionInput,
    db: Session = Depends(get_db),
):
    """Ask the configured vision model for reviewable primary-category suggestions."""
    if not config.vlm_enabled():
        raise HTTPException(
            status_code=503,
            detail="视觉模型未配置，不能生成素材分类建议",
        )
    case_ids = list(dict.fromkeys(payload.case_ids))
    if not case_ids or len(case_ids) > 20:
        raise HTTPException(status_code=400, detail="每次请选择 1～20 个案例")
    cases = (
        db.query(models.Case)
        .filter(models.Case.id.in_(case_ids))
        .order_by(models.Case.id)
        .all()
    )

    tasks = [
        (case.id, config.UPLOAD_DIR / Path(case.image.url).name)
        for case in cases
        if case.image
    ]
    if not tasks:
        raise HTTPException(status_code=400, detail="所选案例没有可分析的原图")

    def classify(task: tuple[int, Path]):
        case_id, path = task
        if not path.exists():
            raise FileNotFoundError("原图不存在")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return case_id, vlm.suggest_asset_category(path.read_bytes(), mime)

    suggestions = []
    failed = []
    with ThreadPoolExecutor(max_workers=min(5, len(tasks))) as pool:
        jobs = {pool.submit(classify, task): task[0] for task in tasks}
        for future in as_completed(jobs):
            case_id = jobs[future]
            try:
                _, result = future.result()
                (
                    db.query(models.AssetCategorySuggestion)
                    .filter(
                        models.AssetCategorySuggestion.case_id == case_id,
                        models.AssetCategorySuggestion.status == "pending",
                    )
                    .update({"status": "superseded"})
                )
                row = models.AssetCategorySuggestion(
                    case_id=case_id,
                    suggested_category=result["category"],
                    confidence=result["confidence"],
                    reason=result["reason"],
                    signals=json.dumps(result["signals"], ensure_ascii=False),
                    model_name=config.VISION_MODEL,
                    status="pending",
                )
                db.add(row)
                db.flush()
                suggestions.append(_serialize_category_suggestion(row))
            except Exception as exc:
                failed.append({"case_id": case_id, "detail": str(exc)})
    db.commit()
    return {
        "suggestions": suggestions,
        "suggested_count": len(suggestions),
        "failed": failed,
    }


def _serialize_category_job(job: models.CategorySuggestionJob) -> dict:
    try:
        errors = json.loads(job.errors or "[]")
    except Exception:
        errors = []
    return {
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "succeeded": job.succeeded,
        "failed": job.failed,
        "errors": errors,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _run_category_suggestion_job(job_id: int, case_ids: list[int]) -> None:
    """Run in FastAPI's background thread and persist progress after every item."""
    db = SessionLocal()
    now = lambda: dt.datetime.now(dt.UTC).replace(tzinfo=None)
    try:
        job = db.get(models.CategorySuggestionJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = now()
        db.commit()

        cases = (
            db.query(models.Case)
            .filter(models.Case.id.in_(case_ids))
            .order_by(models.Case.id)
            .all()
        )
        tasks = [
            (case.id, config.UPLOAD_DIR / Path(case.image.url).name)
            for case in cases
            if case.image
        ]

        def classify(task: tuple[int, Path]):
            case_id, path = task
            if not path.exists():
                raise FileNotFoundError("原图不存在")
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            return case_id, vlm.suggest_asset_category(path.read_bytes(), mime)

        errors = []
        with ThreadPoolExecutor(max_workers=min(5, max(1, len(tasks)))) as pool:
            jobs = {pool.submit(classify, task): task[0] for task in tasks}
            for future in as_completed(jobs):
                case_id = jobs[future]
                try:
                    _, result = future.result()
                    (
                        db.query(models.AssetCategorySuggestion)
                        .filter(
                            models.AssetCategorySuggestion.case_id == case_id,
                            models.AssetCategorySuggestion.status == "pending",
                        )
                        .update({"status": "superseded"})
                    )
                    db.add(
                        models.AssetCategorySuggestion(
                            case_id=case_id,
                            suggested_category=result["category"],
                            confidence=result["confidence"],
                            reason=result["reason"],
                            signals=json.dumps(
                                result["signals"],
                                ensure_ascii=False,
                            ),
                            model_name=config.VISION_MODEL,
                            status="pending",
                        )
                    )
                    job.succeeded += 1
                except Exception as exc:
                    job.failed += 1
                    errors.append({"case_id": case_id, "detail": str(exc)})
                job.completed += 1
                job.errors = json.dumps(errors, ensure_ascii=False)
                db.commit()

        missing = len(case_ids) - len(tasks)
        if missing > 0:
            job.failed += missing
            job.completed += missing
            errors.append(
                {
                    "case_id": None,
                    "detail": f"{missing} 个案例缺少可分析原图",
                }
            )
        job.errors = json.dumps(errors, ensure_ascii=False)
        job.status = "completed" if job.failed == 0 else "completed_with_errors"
        job.finished_at = now()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(models.CategorySuggestionJob, job_id)
        if job:
            job.status = "failed"
            job.errors = json.dumps(
                [{"case_id": None, "detail": str(exc)}],
                ensure_ascii=False,
            )
            job.finished_at = now()
            db.commit()
    finally:
        db.close()


@app.post("/api/training/category-suggestion-jobs")
def create_category_suggestion_job(
    payload: BatchCategorySuggestionInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not config.vlm_enabled():
        raise HTTPException(
            status_code=503,
            detail="视觉模型未配置，不能生成素材分类建议",
        )
    case_ids = list(dict.fromkeys(payload.case_ids))
    if not case_ids or len(case_ids) > 50:
        raise HTTPException(status_code=400, detail="每次请选择 1～50 个案例")
    found = {
        row[0]
        for row in db.query(models.Case.id)
        .filter(models.Case.id.in_(case_ids))
        .all()
    }
    missing = [case_id for case_id in case_ids if case_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"案例不存在：{missing}")
    job = models.CategorySuggestionJob(
        case_ids=json.dumps(case_ids),
        status="queued",
        total=len(case_ids),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_category_suggestion_job, job.id, case_ids)
    return _serialize_category_job(job)


@app.get("/api/training/category-suggestion-job-status")
def latest_category_suggestion_job(db: Session = Depends(get_db)):
    job = (
        db.query(models.CategorySuggestionJob)
        .order_by(models.CategorySuggestionJob.id.desc())
        .first()
    )
    return _serialize_category_job(job) if job else None


@app.get("/api/training/category-suggestion-jobs/{job_id}")
def get_category_suggestion_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.get(models.CategorySuggestionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="分类任务不存在")
    return _serialize_category_job(job)


@app.get("/api/cases/{case_id}/versions")
def case_versions(case_id: int, db: Session = Depends(get_db)):
    exists = db.query(models.Case.id).filter(models.Case.id == case_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="案例不存在")
    versions = (
        db.query(models.AnalysisVersion)
        .filter(models.AnalysisVersion.case_id == case_id)
        .order_by(models.AnalysisVersion.version.desc())
        .all()
    )
    return [
        {
            "version": item.version,
            "source": item.source,
            "model_name": item.model_name,
            "prompt_version": item.prompt_version,
            "editor": item.editor,
            "created_at": item.created_at,
        }
        for item in versions
    ]


@app.post("/api/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    project = models.Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return {
        **payload.model_dump(),
        "id": project.id,
        "case_count": 0,
        "verified_count": 0,
        "recommended_count": 0,
        "created_at": project.created_at,
    }


@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
    result = []
    for project in projects:
        counts = dict(
            db.query(models.Case.trust_status, func.count(models.Case.id))
            .filter(models.Case.project_id == project.id)
            .group_by(models.Case.trust_status)
            .all()
        )
        project_cases = (
            db.query(models.Case)
            .filter(models.Case.project_id == project.id)
            .all()
        )
        result.append(
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "business_line": project.business_line,
                "status": project.status,
                "is_gold": project.is_gold,
                "case_count": sum(counts.values()),
                "verified_count": counts.get("verified", 0),
                "recommended_count": counts.get("company_recommended", 0),
                "model_analyzed_count": sum(
                    1
                    for case in project_cases
                    if case.analysis
                    and case.analysis.model_name
                    and case.analysis.model_name != "启发式规则"
                ),
                "company_published_count": sum(
                    1
                    for case in project_cases
                    if case.image
                    and case.image.source_type == "company_published"
                ),
                "created_at": project.created_at,
            }
        )
    return result


@app.get("/api/training/overview")
def training_overview(db: Session = Depends(get_db)):
    """Operational readiness metrics for the company-preference training loop."""
    trust_rows = dict(
        db.query(models.Case.trust_status, func.count(models.Case.id))
        .group_by(models.Case.trust_status)
        .all()
    )
    category_rows = (
        db.query(
            models.Case.asset_category,
            models.Case.trust_status,
            func.count(models.Case.id),
        )
        .group_by(models.Case.asset_category, models.Case.trust_status)
        .all()
    )
    category_coverage: dict[str, dict[str, int]] = {
        key: {"total": 0, "trusted": 0, "recommended": 0}
        for key in ("layout", "style", "color", "photo")
    }
    for category, trust_status, count in category_rows:
        item = category_coverage.setdefault(
            category or "layout",
            {"total": 0, "trusted": 0, "recommended": 0},
        )
        item["total"] += count
        if trust_status in {"verified", "company_recommended"}:
            item["trusted"] += count
        if trust_status == "company_recommended":
            item["recommended"] += count

    total = sum(trust_rows.values())
    trusted = trust_rows.get("verified", 0) + trust_rows.get(
        "company_recommended", 0
    )
    reviewed = trusted + trust_rows.get("rejected", 0)
    preference_count = db.query(models.PreferenceEvent).count()
    service_rows = dict(
        db.query(models.ServiceRun.status, func.count(models.ServiceRun.id))
        .group_by(models.ServiceRun.status)
        .all()
    )
    business_line_coverage: dict[str, dict[str, int]] = {}
    all_cases = db.query(models.Case).all()
    for case in all_cases:
        line = (case.business_line or case.industry or "未分类").strip() or "未分类"
        item = business_line_coverage.setdefault(
            line,
            {
                "total": 0,
                "model_analyzed": 0,
                "company_published": 0,
                "trusted": 0,
                "recommended": 0,
            },
        )
        item["total"] += 1
        if (
            case.analysis
            and case.analysis.model_name
            and case.analysis.model_name != "启发式规则"
        ):
            item["model_analyzed"] += 1
        if case.image and case.image.source_type == "company_published":
            item["company_published"] += 1
        if case.trust_status in {"verified", "company_recommended"}:
            item["trusted"] += 1
        if case.trust_status == "company_recommended":
            item["recommended"] += 1
    training_matrix = []
    company_training_lines = sorted(
        line
        for line, coverage in business_line_coverage.items()
        if coverage["company_published"] > 0
    )
    project_by_line = {
        project.business_line.strip(): project.id
        for project in db.query(models.Project).all()
        if project.business_line and project.business_line.strip()
    }
    for line in company_training_lines:
        cells = {}
        for category in ("layout", "style", "color", "photo"):
            cell_cases = [
                case
                for case in all_cases
                if (case.business_line or case.industry or "未分类").strip() == line
                and (case.asset_category or "layout") == category
            ]
            published = sum(
                1
                for case in cell_cases
                if case.image and case.image.source_type == "company_published"
            )
            analyzed = sum(
                1
                for case in cell_cases
                if case.analysis
                and case.analysis.model_name
                and case.analysis.model_name != "启发式规则"
            )
            trusted_cell = sum(
                1
                for case in cell_cases
                if case.trust_status in {"verified", "company_recommended"}
            )
            recommended_cell = sum(
                1
                for case in cell_cases
                if case.trust_status == "company_recommended"
            )
            gaps = []
            if published < 2:
                gaps.append(f"补{2 - published}张成品")
            if analyzed < 1:
                gaps.append("完成1张模型拆解")
            if trusted_cell < 1:
                gaps.append("完成1张人工确认")
            cells[category] = {
                "total": len(cell_cases),
                "company_published": published,
                "model_analyzed": analyzed,
                "trusted": trusted_cell,
                "recommended": recommended_cell,
                "ready": not gaps,
                "gaps": gaps,
            }
        training_matrix.append(
            {
                "business_line": line,
                "project_id": project_by_line.get(line),
                "ready_categories": sum(
                    1 for cell in cells.values() if cell["ready"]
                ),
                "cells": cells,
            }
        )
    target_trusted = 30
    target_recommended = 12
    recommended = trust_rows.get("company_recommended", 0)
    maturity = min(
        100,
        round(
            50 * min(trusted / target_trusted, 1)
            + 30 * min(recommended / target_recommended, 1)
            + 20 * min(preference_count / 50, 1)
        ),
    )
    return {
        "total_cases": total,
        "reviewed_cases": reviewed,
        "unreviewed_cases": trust_rows.get("ai_unverified", 0),
        "verified_cases": trust_rows.get("verified", 0),
        "recommended_cases": recommended,
        "rejected_cases": trust_rows.get("rejected", 0),
        "preference_events": preference_count,
        "service_runs": sum(service_rows.values()),
        "adopted_service_runs": service_rows.get("adopted", 0),
        "service_outcomes": service_rows,
        "business_line_coverage": business_line_coverage,
        "training_matrix": training_matrix,
        "maturity_score": maturity,
        "targets": {
            "trusted_cases": target_trusted,
            "recommended_cases": target_recommended,
            "preference_events": 50,
        },
        "category_coverage": category_coverage,
    }


@app.get("/api/training/task-pack")
def training_task_pack(db: Session = Depends(get_db)):
    """Turn training gaps into an assignable weekly execution list."""
    overview = training_overview(db)
    category_names = {
        "layout": "排版",
        "style": "风格",
        "color": "色彩",
        "photo": "实拍图",
    }
    latest_suggestions: dict[int, models.AssetCategorySuggestion] = {}
    for suggestion in (
        db.query(models.AssetCategorySuggestion)
        .order_by(models.AssetCategorySuggestion.id.desc())
        .all()
    ):
        latest_suggestions.setdefault(suggestion.case_id, suggestion)

    tasks = []
    for row in overview["training_matrix"]:
        project_id = row["project_id"]
        project_cases = (
            db.query(models.Case)
            .filter(models.Case.project_id == project_id)
            .order_by(models.Case.id)
            .all()
            if project_id
            else []
        )
        for category, cell in row["cells"].items():
            if cell["ready"]:
                continue
            current_candidates = [
                case.id
                for case in project_cases
                if (case.asset_category or "layout") == category
                and case.trust_status != "rejected"
            ]
            suggestion_candidates = [
                case.id
                for case in project_cases
                if (
                    suggestion := latest_suggestions.get(case.id)
                )
                and suggestion.status == "pending"
                and suggestion.suggested_category == category
            ]
            candidate_ids = list(
                dict.fromkeys(suggestion_candidates + current_candidates)
            )[:5]
            if cell["company_published"] < 2:
                owner_role = "素材管理员"
                next_action = (
                    f"补充并归类 {2 - cell['company_published']} 张"
                    f"{category_names[category]}公司成品"
                )
                priority = "urgent" if cell["company_published"] == 0 else "high"
            elif cell["model_analyzed"] < 1:
                owner_role = "AI运营"
                next_action = "选择1张代表样本完成火山模型深度拆解"
                priority = "high"
            else:
                owner_role = "设计负责人"
                next_action = "审核1张模型拆解并填写保留与规避规则"
                priority = "high"
            tasks.append(
                {
                    "task_id": f"{project_id or 0}-{category}",
                    "business_line": row["business_line"],
                    "project_id": project_id,
                    "asset_category": category,
                    "category_label": category_names[category],
                    "priority": priority,
                    "owner_role": owner_role,
                    "next_action": next_action,
                    "candidate_case_ids": candidate_ids,
                    "current": {
                        "company_published": cell["company_published"],
                        "model_analyzed": cell["model_analyzed"],
                        "trusted": cell["trusted"],
                        "recommended": cell["recommended"],
                    },
                    "acceptance_criteria": [
                        "公司成品不少于2张",
                        "至少1张完成真实视觉模型拆解",
                        "至少1张由设计负责人确认",
                        "确认时填写必须保留与必须规避规则",
                    ],
                }
            )
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    tasks.sort(
        key=lambda item: (
            priority_order.get(item["priority"], 9),
            0 if item["candidate_case_ids"] else 1,
            item["business_line"],
            item["asset_category"],
        )
    )
    return {
        "generated_at": dt.datetime.now(dt.UTC).replace(tzinfo=None),
        "total_tasks": len(tasks),
        "ready_cells": sum(
            row["ready_categories"] for row in overview["training_matrix"]
        ),
        "total_cells": len(overview["training_matrix"]) * 4,
        "tasks": tasks,
    }


@app.get("/api/training/readiness")
def training_readiness(db: Session = Depends(get_db)):
    """Return evidence gates and the next concrete action for every business line."""
    cases = db.query(models.Case).all()
    runs = db.query(models.ServiceRun).all()
    lines = sorted(
        {
            (case.business_line or "").strip()
            for case in cases
            if (case.business_line or "").strip()
        }
        | {run.industry.strip() for run in runs if run.industry.strip()}
    )
    result = []
    for line in lines:
        line_cases = [
            case
            for case in cases
            if (case.business_line or "").strip() == line
        ]
        line_runs = [run for run in runs if run.industry.strip() == line]
        published = sum(
            1
            for case in line_cases
            if case.image and case.image.source_type == "company_published"
        )
        category_counts = {
            category: sum(
                1
                for case in line_cases
                if case.asset_category == category
                and case.image
                and case.image.source_type == "company_published"
            )
            for category in ("layout", "style", "color", "photo")
        }
        category_coverage = {
            category: {"current": count, "target": 2, "met": count >= 2}
            for category, count in category_counts.items()
        }
        covered_categories = sum(
            1 for item in category_coverage.values() if item["met"]
        )
        coverage_gaps = [
            category
            for category, item in category_coverage.items()
            if not item["met"]
        ]
        model_analyzed = sum(
            1
            for case in line_cases
            if case.analysis
            and case.analysis.model_name
            and case.analysis.model_name != "启发式规则"
        )
        verified = sum(
            1
            for case in line_cases
            if case.trust_status in {"verified", "company_recommended"}
        )
        recommended = sum(
            1
            for case in line_cases
            if case.trust_status == "company_recommended"
        )
        adopted_runs = sum(1 for run in line_runs if run.status == "adopted")
        review_candidates = [
            case.id
            for case in line_cases
            if case.trust_status == "ai_unverified"
            and case.analysis
            and case.analysis.model_name
            and case.analysis.model_name != "启发式规则"
        ][:3]
        gates = {
            "company_assets": {
                "current": published,
                "target": 10,
                "met": published >= 10,
            },
            "category_balance": {
                "current": covered_categories,
                "target": 4,
                "met": covered_categories >= 4,
            },
            "model_analyzed": {
                "current": model_analyzed,
                "target": 3,
                "met": model_analyzed >= 3,
            },
            "human_verified": {
                "current": verified,
                "target": 3,
                "met": verified >= 3,
            },
            "company_recommended": {
                "current": recommended,
                "target": 1,
                "met": recommended >= 1,
            },
            "service_runs": {
                "current": len(line_runs),
                "target": 5,
                "met": len(line_runs) >= 5,
            },
            "adopted_runs": {
                "current": adopted_runs,
                "target": 2,
                "met": adopted_runs >= 2,
            },
        }
        if not gates["company_assets"]["met"]:
            stage = "collect"
            next_action = f"再补充 {10 - published} 张代表性公司成品"
        elif not gates["category_balance"]["met"]:
            stage = "organize"
            category_names = {
                "layout": "排版",
                "style": "风格",
                "color": "色彩",
                "photo": "实拍图",
            }
            next_action = "补齐素材类别：" + "、".join(
                category_names[item] for item in coverage_gaps
            )
        elif not gates["model_analyzed"]["met"]:
            stage = "analyze"
            next_action = f"再完成 {3 - model_analyzed} 张火山模型深度拆解"
        elif not gates["human_verified"]["met"]:
            stage = "verify"
            next_action = f"人工确认 {3 - verified} 张模型样本"
        elif not gates["company_recommended"]["met"]:
            stage = "curate"
            next_action = "从已确认样本中选择 1 张公司推荐"
        elif not gates["service_runs"]["met"]:
            stage = "operate"
            next_action = f"完成 {5 - len(line_runs)} 次真实业务方向生成"
        elif not gates["adopted_runs"]["met"]:
            stage = "feedback"
            next_action = f"补充 {2 - adopted_runs} 次真实采用结果"
        else:
            stage = "operational"
            next_action = "已达到初步可运营标准，继续按月复盘和扩充"
        service_mode = (
            "operational"
            if stage == "operational"
            else "pilot"
            if verified >= 3 and recommended >= 1
            else "reference_only"
        )
        weekly_actions = {
            "collect": ["补齐代表性公司成品", "检查品类和业务线标注"],
            "organize": ["将素材按排版、风格、色彩、实拍图重新归类", "每类至少保留 2 张代表样本"],
            "analyze": ["选择差异明显的样本", "调用视觉模型完成结构化拆解"],
            "verify": ["设计负责人逐张核对模型结论", "填写希望延续与应避免规则"],
            "curate": ["从已确认样本中选出黄金标准", "标记为公司推荐"],
            "operate": ["带真实需求生成设计方向", "保存采用、拒绝或修改反馈"],
            "feedback": ["补录实际上线结果", "复盘生成建议与最终成品差异"],
            "operational": ["每月补充新成品", "每月复盘低采用规则并清理过时偏好"],
        }[stage]
        owner_role = {
            "collect": "素材管理员",
            "organize": "素材管理员 / 设计负责人",
            "analyze": "素材管理员 / AI 运营",
            "verify": "设计负责人",
            "curate": "设计总监 / 业务负责人",
            "operate": "需求发起人 / 设计师",
            "feedback": "业务负责人",
            "operational": "素材库运营负责人",
        }[stage]
        score = round(
            15 * min(published / 10, 1)
            + 15 * min(covered_categories / 4, 1)
            + 15 * min(model_analyzed / 3, 1)
            + 20 * min(verified / 3, 1)
            + 15 * min(recommended / 1, 1)
            + 10 * min(len(line_runs) / 5, 1)
            + 10 * min(adopted_runs / 2, 1)
        )
        result.append(
            {
                "business_line": line,
                "stage": stage,
                "score": score,
                "next_action": next_action,
                "gates": gates,
                "service_mode": service_mode,
                "review_candidate_ids": review_candidates,
                "asset_category_coverage": category_coverage,
                "coverage_gaps": coverage_gaps,
                "weekly_actions": weekly_actions,
                "owner_role": owner_role,
                "acceptance_criteria": [
                    "模型拆解与原图一致",
                    "延续项和避坑项均有明确业务理由",
                    "公司推荐样本可作为同品类设计基准",
                    "真实服务结果必须回填采用状态",
                ],
            }
        )
    return result


@app.get("/api/training/review-quality")
def training_review_quality(
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Check technical completeness before a human makes a business decision."""
    query = db.query(models.Case)
    if project_id is not None:
        query = query.filter(models.Case.project_id == project_id)
    cases = query.order_by(models.Case.id).all()
    result = []
    for case in cases:
        analysis = crud.analysis_to_dict(case.analysis) or {}
        layout = analysis.get("layout") or {}
        style = analysis.get("style") or {}
        color = analysis.get("color") or {}
        rules = analysis.get("design_rules") or {}
        score = 0
        warnings = []
        model_name = analysis.get("model_name") or analysis.get("analyzed_by") or ""
        if model_name and model_name != "启发式规则":
            score += 25
        else:
            warnings.append("尚未完成真实视觉模型拆解")
        if layout.get("layout_type"):
            score += 15
        else:
            warnings.append("缺少版式类型")
        if layout.get("hierarchy"):
            score += 10
        else:
            warnings.append("缺少信息层级")
        if style.get("style_tags"):
            score += 10
        else:
            warnings.append("缺少风格标签")
        if color.get("primary") and color.get("palette"):
            score += 10
        else:
            warnings.append("缺少主色或色板")
        if rules.get("why_good"):
            score += 10
        else:
            warnings.append("缺少优秀原因")
        if rules.get("reusable_methods"):
            score += 10
        else:
            warnings.append("缺少可复用方法")
        prompt = analysis.get("prompt") or ""
        if prompt:
            score += 10
        else:
            warnings.append("缺少白板生图提示词")
        result.append(
            {
                "case_id": case.id,
                "score": score,
                "ready": score >= 85,
                "warnings": warnings,
                "model_name": model_name,
                "analysis_version": analysis.get("version") or 0,
            }
        )
    return result


@app.patch("/api/cases/{case_id}/project", response_model=CaseOut)
def assign_case_project(
    case_id: int,
    payload: CaseProjectInput,
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    if payload.project_id is not None:
        project = (
            db.query(models.Project)
            .filter(models.Project.id == payload.project_id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
    case.project_id = payload.project_id
    db.commit()
    db.refresh(case)
    return crud.serialize_case(case)


@app.post("/api/cases/{case_id}/preferences")
def add_preference_event(
    case_id: int,
    payload: PreferenceEventInput,
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    event = models.PreferenceEvent(
        case_id=case.id,
        project_id=case.project_id,
        **payload.model_dump(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, **payload.model_dump(), "created_at": event.created_at}


@app.get("/api/cases/{case_id}/preferences")
def case_preferences(case_id: int, db: Session = Depends(get_db)):
    exists = db.query(models.Case.id).filter(models.Case.id == case_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="案例不存在")
    rows = (
        db.query(models.PreferenceEvent.event_type, func.sum(models.PreferenceEvent.value))
        .filter(models.PreferenceEvent.case_id == case_id)
        .group_by(models.PreferenceEvent.event_type)
        .all()
    )
    return {event_type: int(value or 0) for event_type, value in rows}


@app.post("/api/cases/{case_id}/reanalyze", response_model=CaseOut)
def reanalyze_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case or not case.image:
        raise HTTPException(status_code=404, detail="案例或图片不存在")
    image_path = config.UPLOAD_DIR / Path(case.image.url).name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="原始图片文件不存在")
    try:
        result = run_pipeline(
            str(image_path), asset_category=case.asset_category or "layout"
        )
        case = crud.replace_analysis_from_result(db, case, result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"重新拆解失败：{exc}") from exc
    return crud.serialize_case(case)


@app.get("/api/cases/{case_id}/overlay")
def case_layout_overlay(case_id: int, db: Session = Depends(get_db)):
    """返回叠加了版式骨架（页边距/模块/栅格）的案例图 PNG。"""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case or not case.image:
        raise HTTPException(status_code=404, detail="案例或图片不存在")
    path = config.UPLOAD_DIR / Path(case.image.url).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片文件不存在")
    try:
        png = overlay.render_overlay(str(path))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"骨架渲染失败：{exc}") from exc
    return Response(content=png, media_type="image/png")


@app.get("/api/tags")
def list_tags(db: Session = Depends(get_db)):
    """返回标签及其案例数量，用于首页热门风格 / 检索。"""
    tags = db.query(models.Tag).all()
    return [
        {"id": t.id, "name": t.name, "category": t.category, "count": len(t.cases)}
        for t in tags
    ]


def _analyze_reference(file: UploadFile, data: bytes) -> AnalysisResult:
    """对上传的意向图做视觉拆解（不落库，仅用于推荐）。"""
    ext = Path(file.filename or "").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return run_pipeline(tmp.name)
    finally:
        os.unlink(tmp.name)


@app.post("/api/search", response_model=list[SearchHit])
async def search_assets(
    query_text: str = Form(""),
    product: str = Form(""),
    scene: str = Form(""),
    content_type: str = Form(""),
    source_type: str = Form(""),
    tags: str = Form(""),
    limit: int = Form(60),
    reference_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """文本 + 业务筛选 + 参考图的第一阶段多模态检索。

    当前使用结构化视觉字段进行可解释混合排序；后续替换向量召回时保持此接口不变。
    """
    reference: AnalysisResult | None = None
    if reference_image is not None and (reference_image.filename or ""):
        if not (reference_image.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="参考图必须是图片文件")
        data = await reference_image.read()
        if data:
            try:
                reference = _analyze_reference(reference_image, data)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"参考图解析失败：{exc}") from exc

    results = multimodal_search.search_cases(
        db,
        query_text=query_text,
        product=product,
        scene=scene,
        content_type=content_type,
        source_type=source_type,
        tags=[item.strip() for item in tags.split(",") if item.strip()],
        reference=reference,
        limit=limit,
    )
    return [
        {
            "case": crud.serialize_case(item.case),
            "score": item.score,
            "reasons": item.reasons,
        }
        for item in results
    ]


@app.get("/api/concept")
def get_concept(
    business_line: str = "",
    asset_category: str = "",
    db: Session = Depends(get_db),
):
    """设计视觉概论：跨案例聚合出的分布画像、视觉 DNA 与提炼的设计原则。"""
    return concept.build_concept(
        db,
        business_line=business_line,
        asset_category=normalize_category(asset_category) if asset_category else "",
    )


@app.post("/api/concept/methodology")
def concept_methodology(db: Session = Depends(get_db)):
    """用文本大模型把聚合数据写成成体系的设计方法论（需配置 LLM_*）。"""
    data = concept.build_concept(db)
    try:
        return concept.synthesize_methodology(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"方法论生成失败：{exc}") from exc


@app.post("/api/recommend", response_model=VisualDirection)
async def recommend_direction(
    text: str = Form(""),
    industry: str = Form(""),
    channel: str = Form(""),
    campaign_stage: str = Form(""),
    focus_category: str = Form("layout"),
    business_goal: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """需求生成页：需求文本（+ 可选意向图）→ 推荐视觉方向与绘图提示词。

    对应技术方案「未来升级 V3.0」：需求输入 → 视觉方向 → 意向图生成。
    上传意向图时，会先对其做视觉拆解，并把风格/色彩/排版融合进推荐。
    """
    low = text.lower()
    focus_category = normalize_category(focus_category)
    focus_instruction = category_focus(focus_category)
    context_parts = [
        f"渠道：{channel}" if channel else "",
        f"营销阶段：{campaign_stage}" if campaign_stage else "",
        f"业务目标：{business_goal}" if business_goal else "",
    ]
    business_context = "；".join(part for part in context_parts if part)
    keyword_map = {
        "科技": ["科技感", "冷调", "极简"],
        "高端": ["高级感", "克制", "低饱和"],
        "年轻": ["年轻化", "活力", "高饱和"],
        "温暖": ["温暖感", "亲和", "暖调"],
        "简约": ["极简", "干净", "留白"],
    }
    hit_tags: list[str] = []
    for kw, tags in keyword_map.items():
        if kw in low or kw in industry:
            hit_tags.extend(tags)

    # —— 解析意向图（若有）——
    ref: AnalysisResult | None = None
    if file is not None and (file.filename or ""):
        data = await file.read()
        if data:
            if not (file.content_type or "").startswith("image/"):
                raise HTTPException(status_code=400, detail="意向图必须是图片文件")
            try:
                ref = _analyze_reference(file, data)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"意向图解析失败：{exc}") from exc
            # 意向图：以「排版」为主要参考、风格为次要参考。
            # 排版维度置于标签最前（权重最高），风格与情绪其次。
            layout_tags = [
                ref.layout.layout_type,
                ref.layout.alignment,
                ref.typography.text_ratio,
            ]
            hit_tags = layout_tags + ref.style.style_tags + ref.style.mood_keywords[:2] + hit_tags

    if not hit_tags:
        hit_tags = ["高级感", "极简", "克制"]
    hit_tags = list(dict.fromkeys(hit_tags))

    # 从案例库中检索匹配标签的参考案例
    company_profile = concept.recommendation_context(
        concept.build_concept(
            db,
            business_line=industry,
            asset_category=focus_category,
        ),
        industry=industry,
    )
    ranked_references = multimodal_search.search_cases(
        db,
        query_text=" ".join(
            item
            for item in [
                text,
                industry,
                channel,
                campaign_stage,
                business_goal,
                " ".join(hit_tags),
            ]
            if item
        ),
        reference=ref,
        asset_category=focus_category,
        limit=4,
    )
    refs = [item.case.id for item in ranked_references]

    # —— 组织方向与提示词 ——
    directions: list[str] = []
    if ref is not None:
        # 排版为主要参考 —— 放在第一条，作为生图的核心骨架
        directions.append(
            f"【主要·排版】沿用意向图版式：{ref.layout.layout_type}，{ref.layout.alignment}；"
            f"信息层级：{' → '.join(ref.layout.hierarchy)}"
        )
        directions.append(
            f"【主要·栅格】{ref.layout.grid_columns}；{ref.layout.modules}；"
            f"{ref.layout.margins}；{ref.layout.spacing}"
        )
        directions.append(
            f"【主要·文字】{ref.typography.title_treatment}；字体调性「{ref.typography.font_tone}」；"
            f"{ref.typography.text_ratio}，{ref.typography.size_contrast}"
        )
        # 风格为次要参考
        directions.append(
            f"【次要·风格】风格倾向 {'、'.join(ref.style.style_tags)}，"
            f"色板参考主色 {ref.color.primary}（{'、'.join(ref.color.palette[:3])}），可结合需求微调"
        )
        directions.append(f"情绪关键词：{'、'.join(ref.style.mood_keywords)}")
        palette_hint = "、".join(ref.color.palette[:4])
        # 平台与意向图一致（UI/网页/海报…），避免套电商话术
        p = plat.style_of(ref.basics.image_type, "", ref.basics.scene)
        # 提示词：平台框架 + 排版/信息层级在前（主），风格/色彩在后（次）
        prompt = (
            f"{p['zh']}（{industry or '品牌'}）；"
            f"【版式为主】{ref.layout.layout_type}，{ref.layout.grid_columns}，"
            f"{ref.layout.modules}，{ref.layout.alignment}，{ref.layout.margins}，"
            f"信息层级 {' → '.join(ref.layout.hierarchy)}，{ref.typography.title_treatment}，"
            f"字体{ref.typography.font_tone}；"
            f"【风格为辅】{'、'.join(ref.style.style_tags)}，参考色板 {palette_hint}"
            f"（主色 {ref.color.primary}），{ref.light.type}光影；"
            + (f"需求：{text}；" if text else "")
            + p["quality"]
        )
    else:
        directions = [
            f"主打「{hit_tags[0]}」风格，"
            + ("冷色科技调" if "科技感" in hit_tags else "统一低饱和色板"),
            "构图建议：居中聚焦 + 留白，突出核心信息",
            f"情绪关键词：{'、'.join(hit_tags[1:3]) or '克制、干净'}",
        ]
        # 无意向图：从需求文本/行业推断平台，默认不套电商话术
        p = plat.style_of("", "", f"{text} {industry}")
        prompt = (
            f"{p['zh']}（{industry or '品牌'}），{'、'.join(hit_tags)}风格，"
            + (f"需求：{text}，" if text else "")
            + p["quality"]
        )

    # 需求解读增强：配置了文本模型时，用其把需求+意向图解析成更贴合的方向与提示词
    if company_profile["applied"]:
        company_rule = (
            "公司偏好约束："
            f"优先版式 {'、'.join(company_profile['layouts']) or '以已确认案例为准'}；"
            f"优先风格 {'、'.join(company_profile['styles']) or '以已确认案例为准'}；"
            f"常用色彩 {'、'.join(company_profile['color_families']) or '按业务需求'}。"
        )
        if company_profile.get("keep_rules"):
            company_rule += "必须延续：" + "、".join(company_profile["keep_rules"]) + "。"
        if company_profile.get("avoid_rules"):
            company_rule += "必须避免：" + "、".join(company_profile["avoid_rules"]) + "。"
        directions.insert(0, f"【公司证据】{company_rule}")
        prompt = f"{prompt}；{company_rule}"

    focus_rule = (
        f"本次服务聚焦{category_label(focus_category)}素材仓库：{focus_instruction}"
    )
    directions.insert(0, f"【品类聚焦】{focus_rule}")
    prompt = f"{prompt}；{focus_rule}"

    if config.llm_enabled() and (text.strip() or ref is not None):
        try:
            ref_ctx = ""
            if ref is not None:
                ref_ctx = (
                    f"意向图解析：版式 {ref.layout.layout_type}/{ref.layout.grid_columns}，"
                    f"风格 {'、'.join(ref.style.style_tags)}，主色 {ref.color.primary}。"
                )
            company_ctx = (
                f"公司偏好证据：{company_profile}。"
                if company_profile["applied"]
                else "公司可信样本不足，不得虚构公司偏好。"
            )
            j = llm.chat_json(
                [
                    {"role": "system", "content": "你是资深视觉设计顾问，只输出 JSON，不要多余文字。"},
                    {
                        "role": "user",
                        "content": (
                            company_ctx
                            +
                            f"需求：{text or '（仅意向图，无文字需求）'}；行业：{industry or '未指定'}；"
                            f"{ref_ctx}参考标签：{'、'.join(hit_tags)}。\n"
                            '请输出 JSON：{"directions":["3~4 条以版式为主、风格为辅的视觉方向"],'
                            '"prompt":"一条可直接用于 AI 绘图的中文提示词，版式为主风格为辅"}'
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=900,
            )
            if isinstance(j.get("directions"), list) and j["directions"]:
                directions = [str(x) for x in j["directions"]]
            if j.get("prompt"):
                prompt = str(j["prompt"])
        except Exception:
            pass  # 模型不可用时保留启发式结果

    if company_profile["applied"] and "公司偏好约束" not in prompt:
        directions.insert(0, f"【公司证据】{company_rule}")
        prompt = f"{prompt}；{company_rule}"
    if business_context:
        directions.insert(0, f"【业务约束】{business_context}")
        prompt = f"{prompt}；业务约束：{business_context}"
    if not any("品类聚焦" in item for item in directions):
        directions.insert(0, f"【品类聚焦】{focus_rule}")
    if focus_rule not in prompt:
        prompt = f"{prompt}；{focus_rule}"
    direction = VisualDirection(
        directions=directions,
        recommended_tags=hit_tags,
        reference_case_ids=refs,
        prompt=prompt,
        has_reference=ref is not None,
        reference_style=ref.style.style_tags if ref else [],
        reference_palette=ref.color.palette if ref else [],
        reference_layout=ref.layout.layout_type if ref else "",
        reference_font=ref.typography.font_tone if ref else "",
        reference_summary=ref.summary if ref else "",
        preference_applied=company_profile["applied"],
        company_evidence=company_profile,
        company_maturity=company_profile["evidence_level"],
        company_usage_mode=company_profile["usage_mode"],
        focus_category=focus_category,
        evidence_case_ids=[
            item.case.id
            for item in ranked_references
            if item.case.trust_status in {"verified", "company_recommended"}
            or (
                item.case.image
                and item.case.image.source_type == "company_published"
            )
        ],
    )
    service_run = models.ServiceRun(
        request_text=text,
        industry=industry,
        channel=channel,
        campaign_stage=campaign_stage,
        focus_category=focus_category,
        business_goal=business_goal,
        result_payload=direction.model_dump_json(),
        evidence_case_ids=json.dumps(direction.evidence_case_ids),
        company_profile_snapshot=json.dumps(company_profile, ensure_ascii=False),
    )
    db.add(service_run)
    db.commit()
    db.refresh(service_run)
    return direction.model_copy(update={"run_id": service_run.id})


@app.post("/api/service-runs/{run_id}/feedback")
def service_run_feedback(
    run_id: int,
    payload: ServiceFeedbackInput,
    db: Session = Depends(get_db),
):
    """Close the loop from a generated direction back to its evidence cases."""
    actor = payload.actor.strip()
    if not actor:
        raise HTTPException(status_code=400, detail="反馈人不能为空")
    run = (
        db.query(models.ServiceRun)
        .filter(models.ServiceRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="服务记录不存在")
    previous_status = run.status
    if previous_status == payload.outcome:
        return {
            "run_id": run.id,
            "previous_status": previous_status,
            "status": run.status,
            "evidence_cases_updated": [],
        }
    run.status = payload.outcome
    run.actor = actor
    run.feedback = payload.notes.strip()
    evidence_ids = json.loads(run.evidence_case_ids or "[]")
    outcome_events = {
        "adopted": "adopt",
        "rejected": "reject",
        "needs_revision": "selected",
    }
    event_type = outcome_events[payload.outcome]
    cases = (
        db.query(models.Case)
        .filter(models.Case.id.in_(evidence_ids))
        .all()
        if evidence_ids
        else []
    )
    for case in cases:
        if previous_status in outcome_events:
            db.add(
                models.PreferenceEvent(
                    case_id=case.id,
                    project_id=case.project_id,
                    event_type=outcome_events[previous_status],
                    value=-1,
                    actor=actor,
                    context=f"service_run:{run.id}; superseded by:{payload.outcome}",
                )
            )
        db.add(
            models.PreferenceEvent(
                case_id=case.id,
                project_id=case.project_id,
                event_type=event_type,
                value=1,
                actor=actor,
                context=(
                    f"service_run:{run.id}; outcome:{payload.outcome}; "
                    f"{payload.notes.strip()}"
                ),
            )
        )
    db.commit()
    return {
        "run_id": run.id,
        "previous_status": previous_status,
        "status": run.status,
        "evidence_cases_updated": [case.id for case in cases],
    }


@app.get("/api/service-runs/{run_id}")
def get_service_run(run_id: int, db: Session = Depends(get_db)):
    run = (
        db.query(models.ServiceRun)
        .filter(models.ServiceRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="服务记录不存在")
    return {
        "id": run.id,
        "request_text": run.request_text,
        "industry": run.industry,
        "channel": run.channel,
        "campaign_stage": run.campaign_stage,
        "focus_category": run.focus_category,
        "business_goal": run.business_goal,
        "status": run.status,
        "actor": run.actor,
        "feedback": run.feedback,
        "evidence_case_ids": json.loads(run.evidence_case_ids or "[]"),
        "company_profile_snapshot": json.loads(
            run.company_profile_snapshot or "{}"
        ),
        "result": json.loads(run.result_payload or "{}"),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@app.get("/api/service-runs")
def list_service_runs(limit: int = 30, db: Session = Depends(get_db)):
    runs = (
        db.query(models.ServiceRun)
        .order_by(models.ServiceRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        {
            "id": run.id,
            "request_text": run.request_text,
            "industry": run.industry,
            "channel": run.channel,
            "campaign_stage": run.campaign_stage,
            "focus_category": run.focus_category,
            "business_goal": run.business_goal,
            "status": run.status,
            "actor": run.actor,
            "feedback": run.feedback,
            "evidence_case_ids": json.loads(run.evidence_case_ids or "[]"),
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }
        for run in runs
    ]
