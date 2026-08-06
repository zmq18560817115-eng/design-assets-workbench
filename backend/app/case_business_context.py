"""Minimal, auditable business context for searchable company cases."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from . import layout_patterns, models

REQUIRED_FIELDS = ("content_purpose", "channel", "page_role")


class ContextValidationError(ValueError):
    pass


def _loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def target_blueprints(db: Session) -> dict[int, models.LayoutBlueprint]:
    """The production-searchable verified company cases; Case 228 stays excluded."""
    return {
        row.case_id: row
        for row in layout_patterns.latest_verified_blueprints(db)
        if row.case_id != 228
    }


def _pattern_ids(db: Session, case_id: int) -> list[int]:
    result = []
    for pattern in db.query(models.LayoutPattern).filter_by(review_status="verified").all():
        if case_id in _loads(pattern.evidence_case_ids_json, []):
            result.append(pattern.id)
    return sorted(result)


def _annotation(db: Session, case_id: int) -> models.DisinfectionAnnotation | None:
    direct = (
        db.query(models.DisinfectionAnnotation)
        .filter(models.DisinfectionAnnotation.case_id == case_id)
        .order_by(models.DisinfectionAnnotation.id.desc())
        .first()
    )
    if direct:
        return direct
    for pattern in db.query(models.LayoutPattern).filter_by(review_status="verified").all():
        case_ids = _loads(pattern.evidence_case_ids_json, [])
        annotation_ids = _loads(pattern.evidence_annotation_ids_json, [])
        if case_id in case_ids and len(case_ids) == len(annotation_ids):
            return db.get(models.DisinfectionAnnotation, annotation_ids[case_ids.index(case_id)])
    return None


def source_fingerprint(case: models.Case, blueprint: models.LayoutBlueprint, annotation_id: int | None) -> str:
    raw = f"{case.id}:{case.image_id}:{case.project_id}:{annotation_id}:{blueprint.id}:{blueprint.version}"
    return hashlib.sha256(raw.encode()).hexdigest()


def field_sources(case: models.Case) -> dict[str, Any]:
    return {
        "product_category": {"status": "trusted_import", "source": "case.company_import"},
        "source_type": {"status": "trusted_import", "source": "image.company_import"},
        "project_id": {"status": "trusted_relation", "source": "case.project_id"},
        "image_id": {"status": "trusted_relation", "source": "case.image_id"},
    }


def suggestions(case: models.Case) -> dict[str, Any]:
    analysis = case.analysis
    result: dict[str, Any] = {}
    if case.scene:
        result["use_scene"] = {"value": case.scene, "status": "ai_suggested", "source_analysis_id": analysis.id if analysis else None}
    if case.content_purpose:
        result["content_purpose"] = {"value": case.content_purpose, "status": "ai_suggested", "source_analysis_id": analysis.id if analysis else None}
    if case.channel:
        result["channel"] = {"value": case.channel, "status": "ai_suggested", "source_analysis_id": analysis.id if analysis else None}
    if case.page_role and case.page_role != "other":
        result["page_role"] = {"value": case.page_role, "status": "ai_suggested", "source_analysis_id": analysis.id if analysis else None}
    return result


def preview_initialization(db: Session) -> dict[str, Any]:
    blueprints = target_blueprints(db)
    existing = {row.case_id for row in db.query(models.CaseBusinessContext).all()}
    items = []
    for case_id, blueprint in sorted(blueprints.items()):
        case = db.get(models.Case, case_id)
        annotation = _annotation(db, case_id)
        items.append({
            "case_id": case_id, "blueprint_id": blueprint.id,
            "annotation_id": annotation.id if annotation else None,
            "project_id": case.project_id, "image_id": case.image_id,
            "product_category": case.product_category,
            "evidence_strength": "weak" if case_id == 923 else "standard",
            "will_create": case_id not in existing,
        })
    return {
        "mode": "dry-run", "target_count": len(items),
        "create_count": sum(item["will_create"] for item in items),
        "existing_count": sum(not item["will_create"] for item in items),
        "excluded_case_ids": [228], "items": items,
    }


def initialize_contexts(db: Session) -> dict[str, Any]:
    preview = preview_initialization(db)
    created = events = 0
    try:
        for item in preview["items"]:
            case = db.get(models.Case, item["case_id"])
            blueprint = db.get(models.LayoutBlueprint, item["blueprint_id"])
            sources = field_sources(case)
            sources.update({
                "annotation_id": {"status": "trusted_relation", "value": item["annotation_id"]},
                "blueprint_id": {"status": "trusted_relation", "value": item["blueprint_id"]},
                "formal_pattern_ids": {"status": "trusted_relation", "value": _pattern_ids(db, case.id)},
            })
            fingerprint = source_fingerprint(case, blueprint, item["annotation_id"])
            context = db.query(models.CaseBusinessContext).filter_by(case_id=case.id).first()
            if context and context.source_fingerprint == fingerprint:
                continue
            if context:
                previous = context.confirmation_status
                context.field_sources_json = json.dumps(sources, ensure_ascii=False)
                context.source_fingerprint = fingerprint
                context.version += 1
                db.add(models.CaseBusinessContextEvent(
                    case_id=case.id, action="source_refreshed", previous_state=previous,
                    new_state=context.confirmation_status, changed_fields_json=json.dumps(["field_sources_json", "source_fingerprint"]),
                    field_sources_json=context.field_sources_json,
                    notes="Trusted relation snapshot refreshed; formal business fields unchanged.",
                ))
                events += 1
                continue
            context = models.CaseBusinessContext(
                case_id=case.id, evidence_strength=item["evidence_strength"],
                field_sources_json=json.dumps(sources, ensure_ascii=False),
                suggestion_json=json.dumps(suggestions(case), ensure_ascii=False),
                source_fingerprint=fingerprint,
                confirmation_status="draft",
            )
            db.add(context)
            db.add(models.CaseBusinessContextEvent(
                case_id=case.id, action="initialized", previous_state="not_created",
                new_state="draft", changed_fields_json="[]",
                field_sources_json=context.field_sources_json,
                notes="Initialized from current production-searchable case scope; no AI suggestion accepted.",
            ))
            created += 1
            events += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {**preview, "mode": "execute", "created_count": created, "created_event_count": events}


def missing_fields(context: models.CaseBusinessContext, case: models.Case) -> list[str]:
    missing = []
    if not (case.product_category or "").strip():
        missing.append("product_category")
    sources = _loads(context.field_sources_json, {})
    for field in REQUIRED_FIELDS:
        value = getattr(context, field)
        source = sources.get(field, {})
        if not (value or "").strip() or source.get("status") != "human_confirmed":
            missing.append(field)
    return missing


def serialize_context(db: Session, context: models.CaseBusinessContext, *, include_history: bool = False) -> dict[str, Any]:
    case = db.get(models.Case, context.case_id)
    blueprint = target_blueprints(db).get(context.case_id)
    annotation = _annotation(db, context.case_id)
    result = {
        "id": context.id, "case_id": context.case_id, "case_name": case.name,
        "product_category": case.product_category, "source_type": case.image.source_type if case.image else "",
        "project_id": case.project_id, "image_id": case.image_id,
        "image_url": case.image.url if case.image else "", "annotation_id": annotation.id if annotation else None,
        "blueprint_id": blueprint.id if blueprint else None, "pattern_ids": _pattern_ids(db, context.case_id),
        "use_scene": context.use_scene, "content_purpose": context.content_purpose,
        "channel": context.channel, "page_role": context.page_role,
        "target_audience_json": _loads(context.target_audience_json, None),
        "evidence_strength": context.evidence_strength,
        "field_sources": _loads(context.field_sources_json, {}),
        "suggestions": _loads(context.suggestion_json, {}),
        "confirmation_status": context.confirmation_status,
        "reviewer": context.reviewer, "verified_at": context.verified_at,
        "version": context.version, "missing_fields": missing_fields(context, case),
        "created_at": context.created_at, "updated_at": context.updated_at,
    }
    if include_history:
        result["history"] = [{
            "id": row.id, "action": row.action, "previous_state": row.previous_state,
            "new_state": row.new_state, "changed_fields": _loads(row.changed_fields_json, []),
            "field_sources": _loads(row.field_sources_json, {}), "reviewer": row.reviewer,
            "notes": row.notes, "created_at": row.created_at,
        } for row in db.query(models.CaseBusinessContextEvent).filter_by(case_id=context.case_id).order_by(models.CaseBusinessContextEvent.id).all()]
    return result


def update_contexts(db: Session, case_ids: list[int], values: dict[str, Any], reviewer: str, *, verify: bool = False, notes: str = "") -> list[dict[str, Any]]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ContextValidationError("批量编辑和确认必须填写审核人")
    allowed = {"use_scene", "content_purpose", "channel", "page_role", "target_audience_json"}
    changes = {key: value.strip() if isinstance(value, str) else value for key, value in values.items() if key in allowed and value not in (None, "")}
    if not changes and not verify:
        raise ContextValidationError("没有可保存的字段")
    rows = db.query(models.CaseBusinessContext).filter(models.CaseBusinessContext.case_id.in_(sorted(set(case_ids)))).all()
    if len(rows) != len(set(case_ids)):
        raise ContextValidationError("包含不属于当前目标范围或尚未初始化的案例")
    now = dt.datetime.utcnow()
    try:
        for row in rows:
            before = row.confirmation_status
            sources = _loads(row.field_sources_json, {})
            changed = []
            for field, value in changes.items():
                if getattr(row, field) != value:
                    setattr(row, field, json.dumps(value, ensure_ascii=False) if field == "target_audience_json" else value)
                    sources[field] = {"status": "human_confirmed", "reviewer": reviewer, "confirmed_at": now.isoformat()}
                    changed.append(field)
            row.field_sources_json = json.dumps(sources, ensure_ascii=False)
            row.reviewer = reviewer
            row.version += 1 if changed or verify else 0
            if verify:
                missing = missing_fields(row, db.get(models.Case, row.case_id))
                if missing:
                    raise ContextValidationError(f"Case {row.case_id} 缺少确认字段: {', '.join(missing)}")
                row.confirmation_status = "verified"
                row.verified_at = now
            action = "verified" if verify else "updated"
            if changed or before != row.confirmation_status:
                db.add(models.CaseBusinessContextEvent(
                    case_id=row.case_id, action=action, previous_state=before,
                    new_state=row.confirmation_status,
                    changed_fields_json=json.dumps(changed, ensure_ascii=False),
                    field_sources_json=row.field_sources_json, reviewer=reviewer, notes=notes,
                ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return [serialize_context(db, row, include_history=True) for row in rows]
