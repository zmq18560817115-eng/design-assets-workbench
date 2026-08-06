"""Internal admin routes for minimal searchable-case business context."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import case_business_context as service, models
from .database import get_db

router = APIRouter(prefix="/api/admin/search-case-contexts", tags=["search-case-contexts"])


class ContextBatchInput(BaseModel):
    case_ids: list[int] = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str = ""
    verify: bool = False


@router.get("")
def list_contexts(product_category: str = "", missing_field: str = "", confirmation_status: str = "", source_status: str = "", db: Session = Depends(get_db)):
    target_ids = set(service.target_blueprints(db))
    query = db.query(models.CaseBusinessContext).filter(models.CaseBusinessContext.case_id.in_(target_ids))
    if confirmation_status:
        query = query.filter(models.CaseBusinessContext.confirmation_status == confirmation_status)
    rows = [service.serialize_context(db, row) for row in query.order_by(models.CaseBusinessContext.case_id).all()]
    if product_category:
        rows = [row for row in rows if row["product_category"] == product_category]
    if missing_field:
        rows = [row for row in rows if missing_field in row["missing_fields"]]
    if source_status:
        rows = [row for row in rows if any(value.get("status") == source_status for value in row["field_sources"].values() if isinstance(value, dict))]
    return {"target_count": len(target_ids), "item_count": len(rows), "items": rows}


@router.get("/case/{case_id}")
def get_context(case_id: int, db: Session = Depends(get_db)):
    row = db.query(models.CaseBusinessContext).filter_by(case_id=case_id).first()
    if not row or case_id not in service.target_blueprints(db):
        raise HTTPException(404, "案例不在当前92个检索目标范围")
    return service.serialize_context(db, row, include_history=True)


@router.post("/initialize")
def initialize(execute: bool = False, db: Session = Depends(get_db)):
    return service.initialize_contexts(db) if execute else service.preview_initialization(db)


@router.patch("/batch")
def batch_update(payload: ContextBatchInput, db: Session = Depends(get_db)):
    try:
        items = service.update_contexts(db, payload.case_ids, payload.values, payload.reviewer, verify=payload.verify, notes=payload.notes)
    except service.ContextValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"affected_count": len(items), "items": items}
