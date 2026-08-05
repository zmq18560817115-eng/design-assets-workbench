"""Owner-authorized verification of frozen formal-pattern evidence.

This service is deliberately narrow: it only accepts evidence already frozen in
verified LayoutPatterns.  Dry-run is side-effect free; execute is one database
transaction and rolls back unless the final search gates pass.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from . import candidate_patterns, config, crud, models
from .layout_patterns import latest_verified_blueprints
from .layout_search import _formal_verified_patterns
from .schemas import LayoutBlueprintInput

REVIEWER = "张茗淇"
AUTH_STATUS = "owner_authorized"
AUTH_REASON = "verified_pattern_evidence_batch"
VERIFY_SOURCE = "owner_authorized_verified_pattern_evidence"
VERIFY_NOTES = "由正式公司排版模式证据授权确认，仅用于检索案例资格。"
SPECIAL_LEGACY = {64: 223, 61: 158}
SPECIAL_PRODUCT = {269: 409, 228: 368}
SPECIAL_MISSING = {923: 224}
PATTERN_NAMES = {
    4: "吸奶器·左上产品·右侧说明结构",
    5: "吸奶器·左上产品·下方说明结构",
}


class FormalEvidenceVerificationError(ValueError):
    pass


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readable(path: Path) -> bool:
    try:
        with PILImage.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _project_file_index() -> dict[tuple[str, str], list[Path]]:
    result: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for item in config.PROJECT_DIR.rglob("*"):
        if item.is_file():
            result[(item.name, item.parent.name)].append(item)
    return result


def _annotated_path(annotation: models.DisinfectionAnnotation) -> Path | None:
    current = Path(annotation.annotated_image_path or "")
    if current.is_file():
        return current.resolve()
    if not current.name:
        return None
    matches = _project_file_index().get((current.name, annotation.product_category), [])
    return matches[0].resolve() if len(matches) == 1 else None


def _pairing_payload(db: Session, annotation_id: int) -> tuple[dict[str, Any], models.DisinfectionAnnotationVersion]:
    version = (
        db.query(models.DisinfectionAnnotationVersion)
        .filter_by(annotation_id=annotation_id)
        .order_by(models.DisinfectionAnnotationVersion.version.desc())
        .first()
    )
    if not version:
        raise FormalEvidenceVerificationError("pairing_history_missing")
    return _json(version.payload_json, {}), version


def _pairing_review_index() -> dict[tuple[str, str], dict[str, Any]]:
    path = config.BASE_DIR / "acceptance_data" / "pairing-audit" / "pairing-review.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("items", []):
        values = list(row.values())
        if len(values) >= 9:
            result[(str(values[1]).replace("\\", "/"), str(values[2]).replace("\\", "/"))] = {
                "status": values[3], "basis": values[4], "multiple": values[7],
                "problem": values[8], "raw": row,
            }
    return result


def _human_confirmed(payload: dict[str, Any], version: models.DisinfectionAnnotationVersion) -> bool:
    review = payload.get("pairing_review") or {}
    return payload.get("pairing_status") == "pair_confirmed" and (
        payload.get("pairing_source") == "human_confirmed"
        or (review.get("decision") == "confirmed" and bool(review.get("reviewer")))
        or (version.editor == REVIEWER and review.get("decision") == "confirmed")
    )


def _blueprint_payload(row: models.LayoutBlueprint, *, status: str, editor: str) -> LayoutBlueprintInput:
    values = crud.serialize_layout_blueprint(row)
    return LayoutBlueprintInput.model_validate({
        **values, "review_status": status, "editor": editor,
    })


def _already_verified_by_batch(db: Session, blueprint: models.LayoutBlueprint | None) -> bool:
    if not blueprint or blueprint.review_status != "verified":
        return False
    if not sa_inspect(db.get_bind()).has_table("layout_blueprint_verification_events"):
        return False
    return db.query(models.LayoutBlueprintVerificationEvent).filter_by(
        blueprint_id=blueprint.id, verification_source=VERIFY_SOURCE,
    ).first() is not None


def _modules_from_annotation(annotation: models.DisinfectionAnnotation) -> list[dict[str, Any]]:
    regions = sorted(_json(annotation.regions_json, []), key=lambda item: (item.get("y", 0), item.get("x", 0)))
    first_text = next((item.get("id") for item in regions if item.get("type") == "main_text"), "")
    modules = []
    for priority, region in enumerate(regions, 1):
        source = region.get("type")
        module_type = (
            "layout_block" if source == "layout_block"
            else "product_image" if source == "product_image"
            else "main_title" if region.get("id") == first_text
            else "body_text"
        )
        modules.append({
            "id": str(region.get("id") or f"annotation-{annotation.id}-{priority}"),
            "type": module_type,
            "x": region["x"], "y": region["y"],
            "width": region["width"], "height": region["height"],
            "priority": priority, "importance": priority,
            "alignment": "center", "label": module_type,
            "description": "坐标来自现有彩框标注",
            "content_summary": "owner-authorized annotation transfer",
            "confidence": float(region.get("confidence", 1)),
        })
    return modules


def _annotation_blueprint(annotation: models.DisinfectionAnnotation) -> LayoutBlueprintInput:
    modules = _modules_from_annotation(annotation)
    required = {"layout_block", "product_image", "main_title"}
    if not required.issubset({item["type"] for item in modules}):
        raise FormalEvidenceVerificationError("annotation_required_regions_missing")
    product = next(item for item in modules if item["type"] == "product_image")
    width, height = max(1, annotation.canvas_width), max(1, annotation.canvas_height)
    return LayoutBlueprintInput.model_validate({
        "canvas_ratio": f"{width}:{height}",
        "orientation": annotation.orientation,
        "grid_columns": 6, "grid_rows": 12,
        "margins": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        "alignment": "mixed", "reading_flow": "top-to-bottom",
        "focal_region": {key: product[key] for key in ("x", "y", "width", "height")},
        "information_density": "medium", "text_image_ratio": 0.5,
        "module_count": len(modules), "modules_json": modules,
        "review_status": "corrected", "editor": REVIEWER,
        "model_name": "", "prompt_version": "annotation-transfer-v1",
    })


def _add_product_from_annotation(
    blueprint: models.LayoutBlueprint, annotation: models.DisinfectionAnnotation,
) -> LayoutBlueprintInput:
    values = crud.serialize_layout_blueprint(blueprint)
    modules = list(values["modules_json"])
    if any(item.get("type") == "product_image" for item in modules):
        return _blueprint_payload(blueprint, status="corrected", editor=REVIEWER)
    product_regions = [item for item in _json(annotation.regions_json, []) if item.get("type") == "product_image"]
    if not product_regions:
        raise FormalEvidenceVerificationError("annotation_product_region_missing")
    used_ids = {str(item.get("id")) for item in modules}
    for offset, region in enumerate(product_regions, 1):
        module_id = str(region.get("id") or f"annotation-product-{annotation.id}-{offset}")
        if module_id in used_ids:
            module_id = f"{module_id}-product"
        modules.append({
            "id": module_id, "type": "product_image",
            "x": region["x"], "y": region["y"], "width": region["width"], "height": region["height"],
            "priority": max([int(item.get("priority", 0)) for item in modules] or [0]) + 1,
            "importance": max([int(item.get("importance", 0)) for item in modules] or [0]) + 1,
            "alignment": "center", "label": "产品区域（现有蓝框）",
            "description": "坐标来自现有彩框标注", "content_summary": "annotation product region",
            "confidence": float(region.get("confidence", 1)),
        })
    return LayoutBlueprintInput.model_validate({
        **values, "modules_json": modules, "module_count": len(modules),
        "review_status": "corrected", "editor": REVIEWER,
    })


def _new_blueprint(db: Session, case_id: int, payload: LayoutBlueprintInput) -> models.LayoutBlueprint:
    latest = (
        db.query(models.LayoutBlueprint)
        .filter_by(case_id=case_id)
        .order_by(models.LayoutBlueprint.version.desc())
        .first()
    )
    data = payload.model_dump()
    row = models.LayoutBlueprint(
        case_id=case_id, version=(latest.version + 1) if latest else 1,
        canvas_ratio=data["canvas_ratio"], orientation=data["orientation"],
        grid_columns=data["grid_columns"], grid_rows=data["grid_rows"],
        margins=json.dumps(data["margins"], ensure_ascii=False),
        margins_json=json.dumps(data["margins"], ensure_ascii=False),
        alignment=data["alignment"], reading_flow=data["reading_flow"],
        focal_region=json.dumps(data["focal_region"], ensure_ascii=False) if data["focal_region"] else "",
        information_density=data["information_density"], text_image_ratio=data["text_image_ratio"],
        module_count=data["module_count"], modules_json=json.dumps(data["modules_json"], ensure_ascii=False),
        layout_signature=data["layout_signature"], review_status=data["review_status"],
        model_name=data["model_name"], prompt_version=data["prompt_version"], editor=data["editor"],
    )
    db.add(row)
    db.flush()
    return row


def inspect_batch(db: Session, *, reviewer: str = REVIEWER) -> dict[str, Any]:
    if reviewer != REVIEWER:
        raise FormalEvidenceVerificationError("reviewer_not_authorized")
    patterns = db.query(models.LayoutPattern).filter_by(review_status="verified").order_by(models.LayoutPattern.id).all()
    if len(patterns) != 7:
        raise FormalEvidenceVerificationError(f"expected_7_verified_patterns_got_{len(patterns)}")
    review_index = _pairing_review_index()
    scope: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    auto_authorizable = 0
    for pattern in patterns:
        case_ids = _json(pattern.evidence_case_ids_json, [])
        annotation_ids = _json(pattern.evidence_annotation_ids_json, [])
        if len(case_ids) != len(annotation_ids):
            errors.append({"pattern_id": pattern.id, "reason": "snapshot_length_mismatch"})
            continue
        for case_id, annotation_id in zip(case_ids, annotation_ids):
            item = scope.setdefault(case_id, {"case_id": case_id, "annotation_id": annotation_id, "pattern_ids": []})
            item["pattern_ids"].append(pattern.id)
            if item["annotation_id"] != annotation_id:
                errors.append({"case_id": case_id, "reason": "conflicting_annotation_snapshot"})
    for item in scope.values():
        case = db.get(models.Case, item["case_id"])
        annotation = db.get(models.DisinfectionAnnotation, item["annotation_id"])
        reasons: list[str] = []
        if not case or not annotation or not case.image:
            reasons.append("traceability_missing")
        else:
            resolved = candidate_patterns._case_for_annotation(db, annotation)
            if not resolved or resolved.id != case.id:
                reasons.append("case_annotation_traceability_mismatch")
            if case.product_category != annotation.product_category:
                reasons.append("product_category_mismatch")
            if case.image.source_type != "company_published" or annotation.source_type != "company_published":
                reasons.append("not_company_published")
            original = Path(annotation.original_image_path or "")
            annotated = _annotated_path(annotation)
            if not original.is_file() or not _readable(original):
                reasons.append("original_unreadable")
            if not annotated or not _readable(annotated):
                reasons.append("annotated_unreadable")
            if original.is_file() and case.image.original_sha256 and _sha256(original) != case.image.original_sha256:
                reasons.append("image_sha_mismatch")
            if candidate_patterns._quality_blockers(annotation):
                reasons.append("annotation_quality_blocked")
            payload, version = _pairing_payload(db, annotation.id)
            if payload.get("pairing_status") != "pair_confirmed":
                reasons.append("pairing_not_confirmed")
            source = payload.get("pairing_source")
            item["pairing_source"] = source or "human_review_record"
            if source == "automatic_exact_match":
                key = (
                    str(payload.get("original_relative_path") or "").replace("\\", "/"),
                    str(payload.get("annotation_relative_path") or "").replace("\\", "/"),
                )
                plan = review_index.get(key)
                if not plan:
                    reasons.append("pairing_plan_missing")
                else:
                    if plan["status"] != "exact_match": reasons.append("pairing_not_exact")
                    if str(plan["multiple"]) != "\u5426": reasons.append("pairing_not_unique")
                review = payload.get("pairing_review") or {}
                if review.get("decision") in {"rejected", "reject"}:
                    reasons.append("pairing_human_rejected")
                if not reasons:
                    auto_authorizable += 1
            elif not _human_confirmed(payload, version):
                reasons.append("pairing_not_human_confirmed")
        blueprint = (
            db.query(models.LayoutBlueprint)
            .filter_by(case_id=item["case_id"])
            .order_by(models.LayoutBlueprint.version.desc(), models.LayoutBlueprint.id.desc())
            .first()
        )
        item["blueprint_id"] = blueprint.id if blueprint else None
        if item["case_id"] not in SPECIAL_MISSING:
            if not blueprint:
                reasons.append("blueprint_missing")
            else:
                try:
                    _blueprint_payload(blueprint, status="verified", editor=reviewer)
                except Exception as exc:
                    reasons.append(f"blueprint_schema_invalid:{exc}")
        repaired = _already_verified_by_batch(db, blueprint)
        if item["case_id"] in SPECIAL_LEGACY and not repaired and (not blueprint or blueprint.id != SPECIAL_LEGACY[item["case_id"]]):
            reasons.append("special_legacy_blueprint_changed")
        if item["case_id"] in SPECIAL_PRODUCT and not repaired:
            if not blueprint or blueprint.id != SPECIAL_PRODUCT[item["case_id"]]:
                reasons.append("special_product_blueprint_changed")
            elif annotation:
                try: _annotation_blueprint(annotation)
                except Exception as exc: reasons.append(f"annotation_blueprint_invalid:{exc}")
        if item["case_id"] in SPECIAL_MISSING:
            if blueprint:
                try: _blueprint_payload(blueprint, status="verified", editor=reviewer)
                except Exception as exc: reasons.append(f"blueprint_schema_invalid:{exc}")
            elif annotation:
                try: _annotation_blueprint(annotation)
                except Exception as exc: reasons.append(f"annotation_blueprint_invalid:{exc}")
        item["reasons"] = sorted(set(reasons))
        if item["reasons"]:
            errors.append({"case_id": item["case_id"], "annotation_id": item["annotation_id"], "reasons": item["reasons"]})

    eligible = len(scope) - len({row.get("case_id") for row in errors if row.get("case_id")})
    existing_verified = {row.case_id for row in latest_verified_blueprints(db)}
    predicted_cases = len(existing_verified | {cid for cid, item in scope.items() if not item["reasons"]})
    predicted_patterns = []
    for pattern in patterns:
        ids = _json(pattern.evidence_case_ids_json, [])
        if ids and all(not scope[item]["reasons"] for item in ids):
            predicted_patterns.append(pattern.id)
    categories = Counter()
    for pattern in patterns:
        if pattern.id in predicted_patterns:
            tags = _json(pattern.product_category_tags_json, [])
            categories.update(tags[:1])
    gates = {
        "minimum_searchable_company_cases": predicted_cases >= 50,
        "minimum_searchable_patterns": len(predicted_patterns) >= 5,
        "all_categories": all(categories.get(name, 0) > 0 for name in ("恒温杯", "吸奶器", "羊脂膏")),
    }
    return {
        "mode": "dry-run", "reviewer": reviewer,
        "pattern_count": len(patterns), "evidence_case_count": len(scope),
        "automatic_exact_match_count": sum(item.get("pairing_source") == "automatic_exact_match" for item in scope.values()),
        "automatic_authorizable_count": auto_authorizable,
        "eligible_blueprint_count": eligible, "blocked_count": len(scope) - eligible,
        "predicted_searchable_case_count": predicted_cases,
        "predicted_searchable_pattern_count": len(predicted_patterns),
        "predicted_searchable_pattern_ids": predicted_patterns,
        "category_coverage": dict(categories), "gates": gates,
        # Individual conflicts remain untouched; the batch may proceed only
        # when the resulting eligible subset still clears every search gate.
        "can_execute": all(gates.values()),
        "errors": errors, "items": list(scope.values()),
    }


def _event_state(pattern: models.LayoutPattern) -> dict[str, Any]:
    return {
        "name": pattern.name,
        "version": pattern.version,
        "review_status": pattern.review_status,
        "evidence_case_ids": _json(pattern.evidence_case_ids_json, []),
        "evidence_annotation_ids": _json(pattern.evidence_annotation_ids_json, []),
        "evidence_blueprint_ids": _json(pattern.evidence_blueprint_ids_json, []),
    }


def execute_batch(db: Session, *, reviewer: str = REVIEWER, fail_after: str = "") -> dict[str, Any]:
    preview = inspect_batch(db, reviewer=reviewer)
    if not preview["can_execute"]:
        raise FormalEvidenceVerificationError("dry_run_gates_failed")
    created_verified = created_authorizations = created_events = 0
    try:
        patterns = db.query(models.LayoutPattern).filter_by(review_status="verified").order_by(models.LayoutPattern.id).all()
        scope = {item["case_id"]: item for item in preview["items"]}
        for item in scope.values():
            if item["reasons"]:
                continue
            annotation = db.get(models.DisinfectionAnnotation, item["annotation_id"])
            payload, _ = _pairing_payload(db, annotation.id)
            if payload.get("pairing_source") == "automatic_exact_match":
                auth = db.query(models.PairingAuthorizationEvent).filter_by(
                    annotation_id=annotation.id, authorization_status=AUTH_STATUS,
                    authorization_reason=AUTH_REASON,
                ).first()
                if not auth:
                    db.add(models.PairingAuthorizationEvent(
                        annotation_id=annotation.id,
                        pairing_detection_source="automatic_exact_match",
                        authorization_status=AUTH_STATUS, authorized_by=reviewer,
                        authorization_reason=AUTH_REASON,
                        evidence_json=json.dumps({"pattern_ids": item["pattern_ids"]}),
                    ))
                    created_authorizations += 1

            latest = db.query(models.LayoutBlueprint).filter_by(case_id=item["case_id"]).order_by(models.LayoutBlueprint.version.desc()).first()
            if latest and latest.review_status == "verified":
                verified = latest
            else:
                if item["case_id"] in SPECIAL_LEGACY:
                    corrected = _blueprint_payload(latest, status="corrected", editor=reviewer)
                    latest = _new_blueprint(db, item["case_id"], corrected)
                elif item["case_id"] in SPECIAL_PRODUCT:
                    # Do not mix inferred geometry with the human box geometry:
                    # rebuild the revision solely from the existing red/blue/green boxes.
                    corrected = _annotation_blueprint(annotation)
                    latest = _new_blueprint(db, item["case_id"], corrected)
                elif item["case_id"] in SPECIAL_MISSING and not latest:
                    latest = _new_blueprint(db, item["case_id"], _annotation_blueprint(annotation))
                verified = _new_blueprint(
                    db, item["case_id"],
                    _blueprint_payload(latest, status="verified", editor=reviewer),
                )
                created_verified += 1
            event = db.query(models.LayoutBlueprintVerificationEvent).filter_by(
                blueprint_id=verified.id, verification_source=VERIFY_SOURCE,
            ).first()
            if not event:
                db.add(models.LayoutBlueprintVerificationEvent(
                    blueprint_id=verified.id, case_id=item["case_id"],
                    source_pattern_ids_json=json.dumps(item["pattern_ids"]),
                    reviewer=reviewer, verification_source=VERIFY_SOURCE, notes=VERIFY_NOTES,
                ))
                created_events += 1

        if fail_after == "blueprints":
            raise RuntimeError("test transaction rollback")
        db.flush()
        latest_by_case = {row.case_id: row.id for row in latest_verified_blueprints(db)}
        revised_patterns = 0
        for pattern in patterns:
            before = _event_state(pattern)
            case_ids = _json(pattern.evidence_case_ids_json, [])
            if any(scope[item]["reasons"] for item in case_ids):
                continue
            blueprint_ids = [latest_by_case[item] for item in case_ids]
            target_name = PATTERN_NAMES.get(pattern.id, pattern.name)
            if before["evidence_blueprint_ids"] == blueprint_ids and pattern.name == target_name:
                continue
            pattern.evidence_blueprint_ids_json = json.dumps(blueprint_ids)
            pattern.source_blueprint_ids = json.dumps(blueprint_ids)
            pattern.name = target_name
            pattern.version = (pattern.version or 1) + 1
            pattern.reviewer = reviewer
            pattern.editor = reviewer
            pattern.updated_at = dt.datetime.utcnow()
            after = _event_state(pattern)
            db.add(models.LayoutPatternCandidateReviewEvent(
                candidate_id=pattern.source_candidate_id,
                action="formal_pattern_revision",
                previous_state=json.dumps(before, ensure_ascii=False),
                new_state=json.dumps(after, ensure_ascii=False),
                formal_pattern_id=pattern.id, reviewer=reviewer,
                reviewer_role="design_owner",
                notes="同步最新verified蓝图冻结快照并消除同名模式；Case与Annotation证据集合未变。",
            ))
            revised_patterns += 1
        db.flush()
        searchable_cases = len({row.case_id for row in latest_verified_blueprints(db)})
        searchable_patterns = _formal_verified_patterns(db)
        category_counts = Counter(
            (_json(row.product_category_tags_json, [""]) or [""])[0]
            for row in searchable_patterns
        )
        final_gates = (
            searchable_cases >= 50 and len(searchable_patterns) >= 5
            and all(category_counts.get(name, 0) for name in ("恒温杯", "吸奶器", "羊脂膏"))
        )
        if not final_gates:
            raise FormalEvidenceVerificationError("final_search_gates_failed")
        db.commit()
        return {
            **preview, "mode": "execute", "executed": True,
            "created_authorization_events": created_authorizations,
            "created_verified_blueprints": created_verified,
            "created_verification_events": created_events,
            "revised_patterns": revised_patterns,
            "searchable_case_count": searchable_cases,
            "searchable_pattern_count": len(searchable_patterns),
            "category_coverage": dict(category_counts),
        }
    except Exception:
        db.rollback()
        raise
