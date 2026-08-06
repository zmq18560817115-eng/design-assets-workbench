from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, real_search_acceptance
from .database import get_db
from .schemas import RealSearchAcceptanceFeedbackCreate

router = APIRouter(prefix="/api/layout-search/acceptance", tags=["layout-search-acceptance"])


@router.get("/{dataset_version}")
def detail(dataset_version: str, db: Session = Depends(get_db)):
    dataset = db.query(models.LayoutSearchDataset).filter_by(
        dataset_version=dataset_version
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="验收数据集不存在")
    return real_search_acceptance.acceptance_detail(db, dataset)


@router.post("/{dataset_version}/feedback")
def feedback(
    dataset_version: str,
    payload: RealSearchAcceptanceFeedbackCreate,
    db: Session = Depends(get_db),
):
    try:
        return real_search_acceptance.add_judgment(
            db, dataset_version, **payload.model_dump()
        )
    except real_search_acceptance.AcceptancePreparationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
