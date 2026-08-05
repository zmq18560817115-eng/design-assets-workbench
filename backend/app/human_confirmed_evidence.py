"""Exact-SHA import for one human-confirmed company annotation pairing."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from . import config, imagehash, models

REPAIR_REASON = "human_confirmed_pairing_evidence"
PLAN_DIR = config.BASE_DIR / "acceptance_data" / "pairing-audit"
PLAN_PATHS = (PLAN_DIR / "pairing-import-plan.csv", PLAN_DIR / "paired-assets-full-import-plan.csv")


class EvidenceRepairError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_pairing(db: Session, annotation_id: int) -> dict[str, Any]:
    version = db.query(models.DisinfectionAnnotationVersion).filter_by(
        annotation_id=annotation_id
    ).order_by(models.DisinfectionAnnotationVersion.version.desc()).first()
    if not version:
        raise EvidenceRepairError("标注缺少追加式配对记录")
    payload = json.loads(version.payload_json or "{}")
    if payload.get("pairing_status") != "pair_confirmed":
        raise EvidenceRepairError("配对状态不是pair_confirmed")
    if payload.get("pairing_source") != "human_confirmed":
        raise EvidenceRepairError("配对来源不是human_confirmed")
    reviewer = str((payload.get("pairing_review") or {}).get("reviewer") or version.editor or "").strip()
    if not reviewer:
        raise EvidenceRepairError("人工配对缺少审核人")
    return {**payload, "reviewer": reviewer}


def _plan_evidence(original_relative: str, annotation_relative: str, reviewer: str) -> list[str]:
    matched = []
    for plan in PLAN_PATHS:
        if not plan.is_file():
            raise EvidenceRepairError(f"配对计划不存在: {plan.name}")
        with plan.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        found = False
        for row in rows:
            values = [str(value or "").replace("\\", "/") for value in row.values()]
            if original_relative in values and annotation_relative in values:
                if "pair_confirmed" not in values or "human_confirmed" not in values:
                    raise EvidenceRepairError(f"配对计划状态不一致: {plan.name}")
                if reviewer not in "\n".join(values):
                    raise EvidenceRepairError(f"配对计划审核人不一致: {plan.name}")
                found = True
                break
        if not found:
            raise EvidenceRepairError(f"配对计划未指向同一原图: {plan.name}")
        matched.append(str(plan.resolve()))
    return matched


def _legacy_exact_matches(db: Session, expected_sha256: str) -> list[tuple[models.Image, models.Case | None]]:
    matches: list[tuple[models.Image, models.Case | None]] = []
    for image in db.query(models.Image).all():
        if image.original_sha256 == expected_sha256:
            matches.append((image, image.case))
            continue
        uploaded = config.UPLOAD_DIR / Path(image.url or "").name
        if uploaded.is_file() and _sha256(uploaded) == expected_sha256:
            matches.append((image, image.case))
    return matches


def inspect_repair(
    db: Session,
    *,
    annotation_id: int,
    expected_sha256: str,
    project_id: int,
    reviewer: str,
    product_category: str,
    source_type: str = "company_published",
) -> dict[str, Any]:
    annotation = db.get(models.DisinfectionAnnotation, annotation_id)
    if not annotation:
        raise EvidenceRepairError("annotation_id不存在")
    pairing = _latest_pairing(db, annotation_id)
    if reviewer.strip() != pairing["reviewer"]:
        raise EvidenceRepairError("命令审核人与人工配对审核人不一致")
    if source_type != "company_published" or annotation.source_type != source_type:
        raise EvidenceRepairError("source_type必须为company_published且与标注一致")
    if annotation.product_category != product_category:
        raise EvidenceRepairError("产品品类与标注不一致")
    project = db.get(models.Project, project_id)
    if not project or project.business_line != product_category:
        raise EvidenceRepairError("目标项目不存在或品类不一致")
    original = Path(annotation.original_image_path or "").resolve()
    if not original.is_file() or config.COMPANY_ASSET_ROOT not in original.parents:
        raise EvidenceRepairError("原图不在允许的公司成品目录")
    actual_sha = _sha256(original)
    if actual_sha.lower() != expected_sha256.lower():
        raise EvidenceRepairError("原图SHA与expected SHA不一致")
    original_relative = str(original.relative_to(config.PROJECT_DIR)).replace("\\", "/")
    annotated = Path(annotation.annotated_image_path or "")
    if not annotated.is_file():
        migrated = config.PROJECT_DIR / "产品信息架构图" / product_category / annotated.name
        if migrated.is_file():
            annotated = migrated
    if not annotated.is_file():
        raise EvidenceRepairError("彩框图不存在")
    annotation_relative = f"{product_category}/{annotated.name}"
    version_original = str(pairing.get("original_relative_path") or "").replace("\\", "/")
    version_annotation = str(pairing.get("annotation_relative_path") or "").replace("\\", "/")
    if version_original != original_relative or version_annotation != annotation_relative:
        raise EvidenceRepairError("标注追加记录与当前原图或彩框图不一致")
    plan_paths = _plan_evidence(original_relative, annotation_relative, reviewer)
    exact = _legacy_exact_matches(db, actual_sha)
    if len(exact) > 1:
        raise EvidenceRepairError("精确SHA存在多个Image，禁止自动修复")
    image = case = None
    if exact:
        image, case = exact[0]
        if not case or image.source_type != source_type or case.product_category != product_category:
            raise EvidenceRepairError("精确SHA已有记录但来源或品类不一致")
    target_phash = imagehash.dhash(str(original))
    near = []
    rows = db.query(models.Image.phash, models.Case.id).join(
        models.Case, models.Case.image_id == models.Image.id
    ).filter(models.Image.phash != "").all()
    for other_hash, case_id in rows:
        distance = imagehash.hamming(target_phash, other_hash)
        if distance <= 5:
            other_case = db.get(models.Case, case_id)
            if other_case and other_case.image and other_case.image.original_sha256 == actual_sha:
                continue
            near.append({"case_id": case_id, "distance": distance})
    near.sort(key=lambda item: (item["distance"], item["case_id"]))
    audit = db.query(models.CompanyEvidenceRepairAudit).filter_by(
        annotation_id=annotation_id, original_sha256=actual_sha
    ).first()
    if audit and (not image or not case or audit.image_id != image.id or audit.case_id != case.id):
        raise EvidenceRepairError("现有修复审计与精确SHA记录不一致")
    return {
        "annotation_id": annotation_id,
        "expected_sha256": expected_sha256.lower(), "actual_sha256": actual_sha,
        "source_type": source_type, "product_category": product_category,
        "project_id": project_id, "reviewer": reviewer,
        "original_path": str(original), "annotated_path": str(annotated.resolve()),
        "evidence_paths": [str(original), str(annotated.resolve()), *plan_paths],
        "perceptual_hash": target_phash, "near_duplicates": near,
        "near_duplicate_override": bool(near),
        "near_duplicate_case_id": near[0]["case_id"] if near else None,
        "perceptual_hash_distance": near[0]["distance"] if near else None,
        "override_reason": REPAIR_REASON,
        "existing_image_id": image.id if image else None,
        "existing_case_id": case.id if case else None,
        "existing_audit_id": audit.id if audit else None,
        "would_create_image": 0 if image else 1,
        "would_create_case": 0 if case else 1,
        "would_create_audit": 0 if audit else 1,
        "model_calls": 0,
    }


def execute_repair(db: Session, *, fail_after: str = "", **values: Any) -> dict[str, Any]:
    preview = inspect_repair(db, **values)
    try:
        if preview["existing_audit_id"]:
            return {**preview, "executed": False, "idempotent": True}
        image = db.get(models.Image, preview["existing_image_id"]) if preview["existing_image_id"] else None
        case = db.get(models.Case, preview["existing_case_id"]) if preview["existing_case_id"] else None
        if not image:
            image = models.Image(
                url=f"/api/layout-annotations/{preview['annotation_id']}/original-image",
                filename=Path(preview["original_path"]).name,
                source="human_confirmed_evidence_repair", source_type="company_published",
                source_url=preview["original_path"],
                rights_note="公司内部成品素材；人工确认配对证据修复",
                visibility="team", uploader=preview["reviewer"],
                phash=preview["perceptual_hash"], original_sha256=preview["actual_sha256"],
            )
            db.add(image); db.flush()
        if fail_after == "image":
            raise RuntimeError("test transaction rollback")
        if not case:
            case = models.Case(
                image_id=image.id, project_id=preview["project_id"],
                name=Path(preview["original_path"]).name,
                product_category=preview["product_category"],
                business_line=preview["product_category"], asset_category="layout",
                metadata_status="manual", trust_status="ai_unverified", status="public",
                reviewer=preview["reviewer"],
            )
            db.add(case); db.flush()
        annotation = db.get(models.DisinfectionAnnotation, preview["annotation_id"])
        annotation.case_id = case.id
        db.add(models.CompanyEvidenceRepairAudit(
            annotation_id=annotation.id, image_id=image.id, case_id=case.id,
            original_sha256=preview["actual_sha256"],
            near_duplicate_override=preview["near_duplicate_override"],
            near_duplicate_case_id=preview["near_duplicate_case_id"],
            perceptual_hash_distance=preview["perceptual_hash_distance"],
            evidence_paths_json=json.dumps(preview["evidence_paths"], ensure_ascii=False),
            reviewer=preview["reviewer"], repair_reason=REPAIR_REASON,
        ))
        db.commit()
        return {**preview, "image_id": image.id, "case_id": case.id, "executed": True, "idempotent": False}
    except Exception:
        db.rollback()
        raise
