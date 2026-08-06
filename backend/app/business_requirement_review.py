"""Strict real-brief confirmation and append-only review history."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy.orm import Session

from . import models

REQUIRED = (
    "title", "raw_requirement", "project_id", "product_category", "product_name",
    "channel", "content_purpose", "page_role", "canvas_ratio", "brief_source", "reviewer",
)


def missing_fields(row: models.BusinessRequirement, reviewer: str = "") -> list[str]:
    missing = []
    for field in REQUIRED:
        value = reviewer if field == "reviewer" and reviewer else getattr(row, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def review(db: Session, row: models.BusinessRequirement, *, action: str, reviewer: str, notes: str = "") -> models.BusinessRequirement:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("审核人不能为空")
    if action not in {"confirm", "return"}:
        raise ValueError("不支持的审核操作")
    previous = row.status
    now = dt.datetime.utcnow()
    if action == "confirm":
        missing = missing_fields(row, reviewer)
        if missing:
            raise ValueError(f"需求缺少确认字段: {', '.join(missing)}")
        required = set(json.loads(row.required_modules_json or "[]"))
        forbidden = set(json.loads(row.forbidden_modules_json or "[]"))
        conflict = sorted(required & forbidden)
        if conflict:
            raise ValueError(f"必需模块与禁止模块冲突: {conflict}")
        if not db.get(models.Project, row.project_id):
            raise ValueError("project_id 不存在")
        row.status = "confirmed"
        row.confirmed_at = now
    else:
        row.status = "draft"
        row.confirmed_at = None
    row.reviewer = reviewer
    db.add(models.BusinessRequirementReviewEvent(
        requirement_id=row.id, action=action, previous_state=previous,
        new_state=row.status, changed_fields_json=json.dumps(["status", "reviewer", "confirmed_at"]),
        reviewer=reviewer, notes=notes,
    ))
    db.commit()
    db.refresh(row)
    return row
