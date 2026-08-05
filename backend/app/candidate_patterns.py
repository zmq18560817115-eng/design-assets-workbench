"""Human-reviewed candidate state, append-only audit history and publication."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from . import config, models

CANDIDATE_PATH = config.BASE_DIR / "acceptance_data" / "layout-pattern-discovery" / "layout-pattern-candidates.json"
DECISIONS = {"pending", "keep", "merge", "reject"}
OWNER_ROLE = "design_owner"


class EvidenceAggregationError(ValueError):
    pass


def load_candidates() -> list[dict[str, Any]]:
    data = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    return list(data.get("candidates") or [])


def candidate_map() -> dict[str, dict[str, Any]]:
    return {item["candidate_id"]: item for item in load_candidates()}


def state_dict(row: models.LayoutPatternCandidateReview) -> dict[str, Any]:
    return {
        "decision": row.decision or "pending",
        "owner_confirmed": bool(row.owner_confirmed),
        "owner_reviewer": row.owner_reviewer or "",
        "merge_target_id": row.merge_target_id or "",
        "display_name": row.display_name or "",
        "formal_pattern_id": row.formal_pattern_id,
        "formal_status": row.formal_status or "not_created",
    }


def event_dict(row: models.LayoutPatternCandidateReviewEvent) -> dict[str, Any]:
    return {
        "id": row.id, "candidate_id": row.candidate_id, "action": row.action,
        "previous_state": json.loads(row.previous_state or "{}"),
        "new_state": json.loads(row.new_state or "{}"),
        "merge_target_id": row.merge_target_id or "",
        "formal_pattern_id": row.formal_pattern_id,
        "reviewer": row.reviewer or "", "reviewer_role": row.reviewer_role or "",
        "notes": row.notes or "", "created_at": row.created_at,
    }


def ensure_states(db: Session) -> None:
    """Idempotently import only the observable legacy snapshot, never inferred actions."""
    for candidate in load_candidates():
        candidate_id = candidate["candidate_id"]
        if db.get(models.LayoutPatternCandidateReview, candidate_id):
            continue
        legacy = str(candidate.get("human_review_status") or "")
        decision = {"kept": "keep", "merged": "merge", "rejected": "reject"}.get(legacy, "pending")
        owner_confirmed = legacy == "owner_confirmed"
        row = models.LayoutPatternCandidateReview(
            candidate_id=candidate_id,
            decision=decision,
            owner_confirmed=owner_confirmed,
            owner_reviewer=str(candidate.get("design_owner") or ""),
            merge_target_id=str(candidate.get("merge_target_id") or "") if decision == "merge" else "",
            display_name=str(candidate.get("human_name") or candidate.get("pattern_name_suggestion") or ""),
            formal_status="not_created",
        )
        db.add(row)
        db.flush()
        if legacy:
            snapshot = state_dict(row)
            db.add(models.LayoutPatternCandidateReviewEvent(
                candidate_id=candidate_id, action="legacy_snapshot",
                previous_state="{}", new_state=json.dumps(snapshot, ensure_ascii=False),
                merge_target_id=row.merge_target_id, reviewer=row.owner_reviewer,
                reviewer_role="legacy", notes=f"Migrated observable legacy state only: {legacy}",
            ))
    db.commit()


def _append_event(db: Session, row: models.LayoutPatternCandidateReview, action: str,
                  previous: dict[str, Any], *, reviewer: str, reviewer_role: str,
                  notes: str = "") -> None:
    db.add(models.LayoutPatternCandidateReviewEvent(
        candidate_id=row.candidate_id, action=action,
        previous_state=json.dumps(previous, ensure_ascii=False),
        new_state=json.dumps(state_dict(row), ensure_ascii=False),
        merge_target_id=row.merge_target_id or "", formal_pattern_id=row.formal_pattern_id,
        reviewer=reviewer, reviewer_role=reviewer_role, notes=notes,
    ))


def list_review_candidates(db: Session) -> dict[str, Any]:
    ensure_states(db)
    states = {row.candidate_id: row for row in db.query(models.LayoutPatternCandidateReview).all()}
    events: dict[str, list[dict[str, Any]]] = {}
    for event in db.query(models.LayoutPatternCandidateReviewEvent).order_by(models.LayoutPatternCandidateReviewEvent.id).all():
        events.setdefault(event.candidate_id, []).append(event_dict(event))
    items = []
    for candidate in load_candidates():
        state = states[candidate["candidate_id"]]
        item = {**candidate, **state_dict(state), "history": events.get(candidate["candidate_id"], [])}
        item["pattern_name_suggestion"] = state.display_name or candidate.get("pattern_name_suggestion", "")
        item["missing_requirements"] = publication_missing(db, candidate, state)
        item["evidence_preview"] = evidence_preview(db, candidate["candidate_id"])
        item["current_step"] = 1 if state.decision == "pending" else 2 if not state.owner_confirmed else 3
        item["is_core_pending"] = state.formal_status != "verified" and state.decision not in {"merge", "reject"}
        items.append(item)
    return {
        "candidates": items,
        "counts": {
            "total": len(items),
            "decision_completed": sum(item["decision"] != "pending" for item in items),
            "pending": sum(item["decision"] == "pending" for item in items),
            "owner_confirmed": sum(item["owner_confirmed"] for item in items),
            "formal_patterns": sum(item["formal_status"] in {"draft", "verified"} for item in items),
        },
    }


def apply_action(db: Session, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_states(db)
    candidates = candidate_map()
    candidate = candidates.get(candidate_id)
    row = db.get(models.LayoutPatternCandidateReview, candidate_id)
    if not candidate or not row:
        raise ValueError("候选模式不存在")
    action = str(payload.get("action") or "")
    reviewer = str(payload.get("reviewer") or "").strip()
    role = str(payload.get("reviewer_role") or "reviewer").strip()
    notes = str(payload.get("notes") or "").strip()
    previous = state_dict(row)
    if action in {"keep", "reject"}:
        row.decision = action
        row.merge_target_id = ""
        row.owner_confirmed = False
        row.owner_reviewer = ""
    elif action == "merge":
        target_id = str(payload.get("merge_target_id") or "")
        target = candidates.get(target_id)
        if not target or target_id == candidate_id:
            raise ValueError("合并时必须选择另一个候选模式")
        if target.get("category") != candidate.get("category"):
            raise ValueError("当前阶段禁止跨品类合并；结构相似只能作为提示")
        row.decision, row.merge_target_id = "merge", target_id
        row.owner_confirmed, row.owner_reviewer = False, ""
    elif action == "rename":
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("模式中文名称不能为空")
        row.display_name = name
    elif action == "owner_confirm":
        if row.decision != "keep":
            raise ValueError("必须先选择保留为独立模式")
        if role != OWNER_ROLE or not reviewer:
            raise ValueError("仅设计负责人可以确认")
        row.owner_confirmed, row.owner_reviewer = True, reviewer
    elif action == "owner_unconfirm":
        if role != OWNER_ROLE or not reviewer:
            raise ValueError("仅设计负责人可以取消确认")
        row.owner_confirmed, row.owner_reviewer = False, ""
    elif action == "publish":
        return publish(db, candidate, row, reviewer=reviewer, reviewer_role=role, notes=notes)
    else:
        raise ValueError("非法审核操作")
    db.flush()
    _append_event(db, row, action, previous, reviewer=reviewer, reviewer_role=role, notes=notes)
    db.commit(); db.refresh(row)
    return {**candidate, **state_dict(row), "history": history(db, candidate_id), "missing_requirements": publication_missing(db, candidate, row)}


def history(db: Session, candidate_id: str) -> list[dict[str, Any]]:
    return [event_dict(row) for row in db.query(models.LayoutPatternCandidateReviewEvent).filter_by(candidate_id=candidate_id).order_by(models.LayoutPatternCandidateReviewEvent.id).all()]


def _quality_blockers(annotation: models.DisinfectionAnnotation) -> list[str]:
    if annotation.structure_cluster_key == "needs_box_fix" or annotation.structure_review_status == "needs_box_fix":
        return ["needs_box_fix"]
    regions = json.loads(annotation.regions_json or "[]")
    required = {"layout_block", "product_image", "main_text"}
    return [f"missing:{kind}" for kind in sorted(required - {item.get("type") for item in regions})]


def _case_for_annotation(db: Session, annotation: models.DisinfectionAnnotation) -> models.Case | None:
    linked_case_id = getattr(annotation, "case_id", None)
    if linked_case_id:
        linked = db.get(models.Case, linked_case_id)
        if (
            linked
            and linked.product_category == annotation.product_category
            and linked.image
            and linked.image.source_type == "company_published"
        ):
            return linked
        return None
    original = Path(annotation.original_image_path or "")
    if not original.name:
        return None
    matches = db.query(models.Case).join(models.Image).filter(
        models.Image.filename == original.name,
        models.Image.source_type == "company_published",
        models.Case.product_category == annotation.product_category,
    ).all()
    if original.is_file():
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        for case in matches:
            uploaded = (config.UPLOAD_DIR / Path(case.image.url or "").name).resolve()
            if uploaded.is_file() and hashlib.sha256(uploaded.read_bytes()).hexdigest() == digest:
                return case
    return matches[0] if len(matches) == 1 else None


def evidence(db: Session, candidate: dict[str, Any]) -> tuple[list[models.DisinfectionAnnotation], list[int], list[int]]:
    annotation_ids = list(dict.fromkeys(candidate.get("evidence_annotation_ids") or []))
    annotations = db.query(models.DisinfectionAnnotation).filter(models.DisinfectionAnnotation.id.in_(annotation_ids)).all()
    by_id = {row.id: row for row in annotations}
    ordered = [by_id[item] for item in annotation_ids if item in by_id]
    case_ids, blueprint_ids = [], []
    for annotation in ordered:
        case = _case_for_annotation(db, annotation)
        if case and case.id not in case_ids:
            case_ids.append(case.id)
            blueprint = db.query(models.LayoutBlueprint).filter_by(case_id=case.id).order_by(models.LayoutBlueprint.version.desc()).first()
            if blueprint:
                blueprint_ids.append(blueprint.id)
    return ordered, case_ids, blueprint_ids


def aggregate_evidence(db: Session, root_candidate_id: str) -> dict[str, Any]:
    """Resolve the complete merge graph into one immutable publication snapshot."""
    candidates = candidate_map()
    states = {row.candidate_id: row for row in db.query(models.LayoutPatternCandidateReview).all()}
    root = candidates.get(root_candidate_id)
    root_state = states.get(root_candidate_id)
    if not root or not root_state:
        raise EvidenceAggregationError("根候选不存在")
    if root_state.decision != "keep":
        raise EvidenceAggregationError("正式证据根候选必须是keep状态")

    terminal_cache: dict[str, str] = {}
    def terminal(candidate_id: str, path: tuple[str, ...] = ()) -> str:
        if candidate_id in terminal_cache:
            return terminal_cache[candidate_id]
        if candidate_id in path:
            raise EvidenceAggregationError(f"循环合并: {' -> '.join((*path, candidate_id))}")
        candidate = candidates.get(candidate_id)
        state = states.get(candidate_id)
        if not candidate or not state:
            raise EvidenceAggregationError(f"合并目标不存在: {candidate_id}")
        if state.decision == "reject":
            raise EvidenceAggregationError(f"reject候选不能进入聚合: {candidate_id}")
        if state.decision == "keep":
            terminal_cache[candidate_id] = candidate_id
            return candidate_id
        if state.decision != "merge" or not state.merge_target_id:
            raise EvidenceAggregationError(f"无根合并链: {candidate_id}")
        target = candidates.get(state.merge_target_id)
        if not target:
            raise EvidenceAggregationError(f"合并目标不存在: {state.merge_target_id}")
        if target.get("category") != candidate.get("category"):
            raise EvidenceAggregationError(f"跨品类合并: {candidate_id} -> {state.merge_target_id}")
        resolved = terminal(state.merge_target_id, (*path, candidate_id))
        terminal_cache[candidate_id] = resolved
        return resolved

    for candidate_id, state in states.items():
        if state.decision == "merge":
            terminal(candidate_id)
    source_ids = [root_candidate_id] + sorted(
        candidate_id for candidate_id, state in states.items()
        if state.decision == "merge" and terminal(candidate_id) == root_candidate_id
    )
    if any(candidates[item]["category"] != root["category"] for item in source_ids):
        raise EvidenceAggregationError("聚合包含跨品类候选")

    raw_annotation_ids = [
        annotation_id for candidate_id in source_ids
        for annotation_id in candidates[candidate_id].get("evidence_annotation_ids", [])
    ]
    annotation_ids = list(dict.fromkeys(raw_annotation_ids))
    aggregate = {**root, "evidence_annotation_ids": annotation_ids}
    annotations, case_ids, blueprint_ids = evidence(db, aggregate)
    found_ids = {item.id for item in annotations}
    missing_annotation_ids = [item for item in annotation_ids if item not in found_ids]
    if missing_annotation_ids:
        raise EvidenceAggregationError(f"无法追溯的标注: {missing_annotation_ids}")
    blocked = [item.id for item in annotations if _quality_blockers(item)]
    if blocked:
        raise EvidenceAggregationError(f"needs_box_fix证据: {blocked}")
    non_company = [item.id for item in annotations if item.source_type != "company_published"]
    if non_company:
        raise EvidenceAggregationError(f"非company_published证据: {non_company}")
    annotation_cases = []
    for annotation in annotations:
        case = _case_for_annotation(db, annotation)
        if not case:
            raise EvidenceAggregationError(f"无法追溯公司案例的标注: {annotation.id}")
        if not case.image or case.image.source_type != "company_published":
            raise EvidenceAggregationError(f"非company_published案例: {case.id}")
        annotation_cases.append({"annotation_id": annotation.id, "case_id": case.id})
    if len(case_ids) < 3:
        raise EvidenceAggregationError("去重后少于3个公司案例")
    _, own_case_ids, _ = evidence(db, root)
    return {
        "root_candidate_id": root_candidate_id,
        "source_candidate_ids": source_ids,
        "merged_candidate_count": len(source_ids) - 1,
        "own_case_count": len(own_case_ids),
        "raw_annotation_count": len(raw_annotation_ids),
        "annotation_ids": annotation_ids,
        "case_ids": case_ids,
        "blueprint_ids": blueprint_ids,
        "annotation_cases": annotation_cases,
        "deduplicated_count": len(raw_annotation_ids) - len(annotation_ids),
        "case_deduplicated_count": len(annotation_cases) - len(case_ids),
        "excluded_evidence": [],
        "evidence_count": len(case_ids),
    }


def evidence_preview(db: Session, candidate_id: str) -> dict[str, Any]:
    try:
        return {**aggregate_evidence(db, candidate_id), "errors": []}
    except EvidenceAggregationError as exc:
        candidate = candidate_map().get(candidate_id, {})
        _, case_ids, _ = evidence(db, candidate) if candidate else ([], [], [])
        return {
            "root_candidate_id": candidate_id,
            "source_candidate_ids": [candidate_id] if candidate else [],
            "merged_candidate_count": 0,
            "own_case_count": len(case_ids),
            "evidence_count": len(case_ids), "case_ids": case_ids,
            "annotation_ids": list(dict.fromkeys(candidate.get("evidence_annotation_ids", []))),
            "deduplicated_count": 0, "case_deduplicated_count": 0,
            "excluded_evidence": [], "errors": [str(exc)],
        }


def publication_missing(db: Session, candidate: dict[str, Any], row: models.LayoutPatternCandidateReview) -> list[str]:
    missing = []
    if row.decision != "keep": missing.append("候选尚未明确保留")
    if not row.owner_confirmed: missing.append("设计负责人尚未确认")
    if not (row.display_name or candidate.get("pattern_name_suggestion", "")).strip(): missing.append("模式中文名称缺失")
    if not str(candidate.get("category") or "").strip(): missing.append("产品品类缺失")
    if not candidate.get("suitable_pages") or not candidate.get("unsuitable_pages"): missing.append("适用或不适用场景缺失")
    if not str(candidate.get("reading_order") or "").strip(): missing.append("阅读顺序缺失")
    required, optional = candidate.get("required_modules"), candidate.get("optional_modules")
    if not isinstance(required, list) or not required or not isinstance(optional, list): missing.append("必需模块或可选模块不合法")
    if row.decision == "keep":
        try:
            aggregate_evidence(db, candidate["candidate_id"])
        except EvidenceAggregationError as exc:
            missing.append(str(exc))
    return missing


def _modules(annotation: models.DisinfectionAnnotation) -> list[dict[str, Any]]:
    regions = sorted(json.loads(annotation.regions_json or "[]"), key=lambda item: (item.get("y", 0), item.get("x", 0)))
    first_text = next((item.get("id") for item in regions if item.get("type") == "main_text"), "")
    result = []
    for index, region in enumerate(regions, 1):
        kind = region.get("type")
        module_type = "main_title" if kind == "main_text" and region.get("id") == first_text else "body_text" if kind == "main_text" else kind
        result.append({**region, "type": module_type, "priority": index, "importance": index,
                       "label": module_type, "alignment": "center", "description": "候选代表案例结构",
                       "content_summary": "来源于本地公司案例结构标注", "confidence": float(region.get("confidence", 1))})
    return result


def publish(db: Session, candidate: dict[str, Any], row: models.LayoutPatternCandidateReview,
            *, reviewer: str, reviewer_role: str, notes: str = "") -> dict[str, Any]:
    if reviewer_role != OWNER_ROLE or not reviewer:
        raise ValueError("仅设计负责人可以创建并发布正式模式")
    existing = db.query(models.LayoutPattern).filter_by(source_candidate_id=row.candidate_id).first()
    if existing:
        row.formal_pattern_id, row.formal_status = existing.id, existing.review_status
        db.commit()
        return {**candidate, **state_dict(row), "history": history(db, row.candidate_id), "missing_requirements": []}
    missing = publication_missing(db, candidate, row)
    if missing:
        raise ValueError("；".join(missing))
    snapshot = aggregate_evidence(db, row.candidate_id)
    annotation_ids = snapshot["annotation_ids"]
    case_ids = snapshot["case_ids"]
    blueprint_ids = snapshot["blueprint_ids"]
    annotations = db.query(models.DisinfectionAnnotation).filter(models.DisinfectionAnnotation.id.in_(annotation_ids)).all()
    representative_id = (candidate.get("representative_ids") or [annotations[0].id])[0]
    representative = next((item for item in annotations if item.id == representative_id), annotations[0])
    modules = _modules(representative)
    previous = state_dict(row)
    pattern = models.LayoutPattern(
        name=(row.display_name or candidate["pattern_name_suggestion"]).strip(),
        pattern_code=f"reviewed-candidate:{row.candidate_id}",
        description=f"由人工确认候选 {row.candidate_id} 发布。",
        canvas_ratio=f"{representative.canvas_width}:{representative.canvas_height}",
        orientation=representative.orientation or "square", grid_columns=6, grid_rows=12,
        margins="{}", alignment="mixed", reading_flow=candidate["reading_order"],
        information_density=candidate.get("average_information_density", ""),
        text_image_ratio=0.5, module_count=len(modules), modules_json=json.dumps(modules, ensure_ascii=False),
        module_structure_json=json.dumps(modules, ensure_ascii=False), average_positions_json=json.dumps(modules, ensure_ascii=False),
        required_modules_json=json.dumps(candidate["required_modules"], ensure_ascii=False),
        optional_modules_json=json.dumps(candidate["optional_modules"], ensure_ascii=False),
        suitable_scenes_json=json.dumps(candidate["suitable_pages"], ensure_ascii=False),
        unsuitable_scenes_json=json.dumps(candidate["unsuitable_pages"], ensure_ascii=False),
        evidence_case_ids_json=json.dumps(case_ids), evidence_blueprint_ids_json=json.dumps(blueprint_ids),
        evidence_annotation_ids_json=json.dumps(annotation_ids), evidence_count=len(case_ids),
        source_candidate_ids_json=json.dumps(snapshot["source_candidate_ids"], ensure_ascii=False),
        source_case_ids=json.dumps(case_ids), source_blueprint_ids=json.dumps(blueprint_ids),
        product_category_tags_json=json.dumps([candidate["category"]], ensure_ascii=False),
        business_context_json=json.dumps({"product_categories": [candidate["category"]]}, ensure_ascii=False),
        business_context_review_status="verified", business_context_reviewer=reviewer,
        confidence_level="medium" if len(case_ids) >= 5 else "candidate",
        discovery_method="reviewed-candidate-v1", source_candidate_id=row.candidate_id,
        review_status="verified", reviewer=reviewer, editor=reviewer,
        model_name="human-reviewed-candidate", prompt_version="candidate-publish-v1",
        generated_at=dt.datetime.utcnow(), usage_notes="；".join(candidate["suitable_pages"]),
    )
    db.add(pattern); db.flush()
    row.formal_pattern_id, row.formal_status = pattern.id, "draft"
    _append_event(db, row, "formal_pattern_created", previous, reviewer=reviewer, reviewer_role=reviewer_role, notes=notes)
    before_verify = state_dict(row)
    row.formal_status = "verified"
    _append_event(db, row, "formal_verified", before_verify, reviewer=reviewer, reviewer_role=reviewer_role, notes=notes)
    db.commit(); db.refresh(row)
    return {**candidate, **state_dict(row), "history": history(db, row.candidate_id), "missing_requirements": []}
