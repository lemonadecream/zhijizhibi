"""Target Job API routes (Phase 3).

Endpoints (all under /api/target-job, user-isolated via JWT):
  GET    /home            -> home state (has_target + list + current + match summary)
  POST   /create          -> create a target_job (from Explore direction or blank)
  POST   /parse           -> F9 parse a raw JD into a draft structured model
  PUT    /{id}            -> user confirms/edits the structured JD -> official model
  GET    /{id}            -> get a target_job detail
  DELETE /{id}            -> delete a target_job
  POST   /{id}/set-current -> switch the workspace's "current" job (P1 fix)
  POST   /{id}/match      -> run F10 match + F11 gaps (program computes score)
  GET    /{id}/match      -> read the persisted match + gaps

All routes enforce current_user isolation; AI failures degrade per service layer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.services import jd_service, match_service

router = APIRouter(prefix="/target-job", tags=["target-job"])


# ----------------------------- request models -----------------------------
class CreateIn(BaseModel):
    direction_id: int | None = None
    job_id: int | None = None
    job_title: str = ""
    company: str = ""
    city: str = ""
    raw_jd: str = ""


class ParseIn(BaseModel):
    target_job_id: int
    raw_jd: str = Field(min_length=1)
    job_title: str = ""
    company: str = ""
    city: str = ""
    direction_id: int | None = None


class ConfirmIn(BaseModel):
    ability_model: dict = Field(default_factory=dict)
    industry: str = ""
    responsibilities: list[str] | None = None
    other_requirements: list[str] | None = None
    job_title: str = ""
    company: str = ""
    city: str = ""


# ----------------------------- routes -----------------------------
@router.get("/home")
def get_home(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    listing = jd_service.list_target_jobs(db, user_id=user_id)
    current = listing["current"]
    match_summary = None
    if current:
        match = match_service.get_match(db, user_id=user_id, target_job_id=current["target_job_id"])
        if match:
            match_summary = {
                "total_score": match["match"]["total_score"],
                "ai_status": match["match"]["ai_status"],
                "gap_count": len(match["gaps"]),
            }
    return {
        "has_target": current is not None,
        "items": listing["items"],
        "current": current,
        "match_summary": match_summary,
    }


@router.post("/create")
def post_create(req: CreateIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return jd_service.create_target_job_entry(
        db, user_id=user_id, direction_id=req.direction_id, job_id=req.job_id,
        job_title=req.job_title, company=req.company, city=req.city, raw_jd=req.raw_jd,
    )


@router.post("/parse")
def post_parse(req: ParseIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return jd_service.parse_jd(
        db, user_id=user_id, target_job_id=req.target_job_id, raw_jd=req.raw_jd,
        job_title=req.job_title, company=req.company, city=req.city,
        direction_id=req.direction_id,
    )


@router.put("/{target_job_id}")
def put_confirm(
    target_job_id: int, req: ConfirmIn, db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return jd_service.confirm_target_job(
        db, user_id=user_id, target_job_id=target_job_id,
        ability_model=req.ability_model, industry=req.industry,
        responsibilities=req.responsibilities, other_requirements=req.other_requirements,
        job_title=req.job_title, company=req.company, city=req.city,
    )


@router.get("/{target_job_id}")
def get_detail(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return jd_service.get_target_job_detail(db, user_id=user_id, target_job_id=target_job_id)


@router.delete("/{target_job_id}")
def delete_entry(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return jd_service.delete_target_job_entry(db, user_id=user_id, target_job_id=target_job_id)


@router.post("/{target_job_id}/set-current")
def post_set_current(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return jd_service.set_current_target_job(db, user_id=user_id, target_job_id=target_job_id)


@router.post("/{target_job_id}/match")
def post_match(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return match_service.run_match(db, user_id=user_id, target_job_id=target_job_id)


@router.get("/{target_job_id}/match")
def get_match(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    match = match_service.get_match(db, user_id=user_id, target_job_id=target_job_id)
    if match is None:
        return {"match": None, "gaps": []}
    return match
