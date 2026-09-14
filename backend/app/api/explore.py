"""Explore API routes (Phase 2).

Endpoints (all under /api/explore, user-isolated via JWT):
  GET    /state                  -> home state (profile summary + recs + explore state)
  GET    /recommendations        -> recompute + return ranked, active recommendations
  POST   /preferences/text       -> parse natural-language preference, recompute
  POST   /directions/{id}/exclude -> mark / unmark "not interested"
  POST   /directions/{id}/candidate -> toggle candidate (saved) direction
  POST   /directions/{id}/compare   -> toggle compare selection (max 4)
  POST   /compare                -> set compare selection explicitly
  GET    /compare                -> compare rows + neutral advice
  GET    /directions/{id}        -> direction detail (industries + jobs)
  GET    /industries/{id}        -> industry detail (jobs)
  GET    /jobs/{id}              -> job detail
  POST   /target                 -> set target direction (state migration only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.errors.exceptions import NotFoundError
from app.services import explore_service as svc

router = APIRouter(prefix="/explore", tags=["explore"])


class PrefTextIn(BaseModel):
    text: str


class ExcludeIn(BaseModel):
    excluded: bool = True


class CompareSetIn(BaseModel):
    direction_ids: list[int]


class TargetIn(BaseModel):
    direction_id: int


@router.get("/state")
def get_state(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_explore_home(db, user_id=user_id)


@router.get("/recommendations")
def get_recommendations(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return {"recommendations": svc.compute_recommendations(db, user_id=user_id, with_reason=True)}


@router.post("/preferences/text")
def post_preference_text(
    req: PrefTextIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    return svc.update_preference_text(db, user_id=user_id, text=req.text)


@router.post("/directions/{direction_id}/exclude")
def post_exclude(
    direction_id: int, req: ExcludeIn, db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return svc.exclude_direction(db, user_id=user_id, direction_id=direction_id, excluded=req.excluded)


@router.post("/directions/{direction_id}/candidate")
def post_candidate(
    direction_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    return svc.toggle_candidate(db, user_id=user_id, direction_id=direction_id)


@router.post("/directions/{direction_id}/compare")
def post_compare_toggle(
    direction_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    return svc.toggle_compare(db, user_id=user_id, direction_id=direction_id)


@router.post("/compare")
def post_compare(
    req: CompareSetIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    return svc.set_compare(db, user_id=user_id, direction_ids=req.direction_ids)


@router.get("/compare")
def get_compare(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_compare(db, user_id=user_id)


@router.get("/directions/{direction_id}")
def get_direction_detail(direction_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_direction_detail(db, direction_id=direction_id)


@router.get("/industries/{industry_id}")
def get_industry_detail(industry_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_industry_detail(db, industry_id=industry_id)


@router.get("/jobs/{job_id}")
def get_job_detail(job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_job_detail(db, job_id=job_id)


@router.post("/target")
def post_target(
    req: TargetIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    return svc.set_target_direction(db, user_id=user_id, direction_id=req.direction_id)
