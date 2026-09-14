"""Tracking API routes (Phase 5: F15 投递记录 / F16 面试记录).

Endpoints (all under /api/tracking, user-isolated via JWT):
  GET    /overview              -> counts + upcoming interviews + recent applications
  GET    /applications          -> list applications (optional `status` filter)
  POST   /applications          -> create an application
  GET    /applications/{id}     -> application detail (interviews + merged timeline)
  PUT    /applications/{id}     -> update an application (status machine enforced)
  DELETE /applications/{id}     -> delete an application (cascades interviews)
  POST   /applications/{id}/interviews   -> add an interview to an application
  PUT    /interviews/{id}       -> update an interview (result links to application)
  DELETE /interviews/{id}       -> delete an interview

All routes enforce current_user isolation (repositories re-check ownership).
Pure program logic: no AI, no external services.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.services import tracking_service as svc

router = APIRouter(prefix="/tracking", tags=["tracking"])


# ----------------------------- request models -----------------------------
class ApplicationIn(BaseModel):
    company: str
    job_title: str
    city: str | None = None
    job_url: str | None = None
    source: str | None = None
    applied_at: str | None = None  # YYYY-MM-DD
    status: str = "drafted"
    next_action: str | None = None
    next_action_at: str | None = None
    note: str = ""
    target_job_id: int | None = None


class ApplicationUpdateIn(BaseModel):
    company: str | None = None
    job_title: str | None = None
    city: str | None = None
    job_url: str | None = None
    source: str | None = None
    applied_at: str | None = None
    status: str | None = None
    next_action: str | None = None
    next_action_at: str | None = None
    note: str | None = None
    target_job_id: int | None = None


class InterviewIn(BaseModel):
    round: str | None = None
    interview_type: str | None = None
    scheduled_at: str | None = None  # ISO datetime
    interviewer: str | None = None
    status: str = "scheduled"
    result: str = "pending"
    note: str | None = None


class InterviewUpdateIn(BaseModel):
    round: str | None = None
    interview_type: str | None = None
    scheduled_at: str | None = None
    status: str | None = None
    result: str | None = None
    interviewer: str | None = None
    note: str | None = None


# ----------------------------- routes -----------------------------
@router.get("/overview")
def get_overview(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.get_tracking_overview(db, user_id=user_id)


@router.get("/applications")
def list_applications(status: str | None = Query(default=None),
                      db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.list_applications(db, user_id=user_id, status=status)


@router.post("/applications")
def create_application(req: ApplicationIn, db: Session = Depends(get_db),
                       user_id: int = Depends(get_current_user_id)):
    return svc.create_application_entry(
        db, user_id=user_id,
        company=req.company, job_title=req.job_title, city=req.city, job_url=req.job_url,
        source=req.source, applied_at=req.applied_at, status=req.status,
        next_action=req.next_action, next_action_at=req.next_action_at,
        note=req.note, target_job_id=req.target_job_id,
    )


@router.get("/applications/{application_id}")
def get_application(application_id: int, db: Session = Depends(get_db),
                    user_id: int = Depends(get_current_user_id)):
    return svc.get_application_detail(db, user_id=user_id, application_id=application_id)


@router.put("/applications/{application_id}")
def update_application(application_id: int, req: ApplicationUpdateIn,
                       db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    return svc.update_application_entry(
        db, user_id=user_id, application_id=application_id, **fields
    )


@router.delete("/applications/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db),
                       user_id: int = Depends(get_current_user_id)):
    return svc.delete_application_entry(db, user_id=user_id, application_id=application_id)


@router.post("/applications/{application_id}/interviews")
def create_interview(application_id: int, req: InterviewIn, db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user_id)):
    return svc.create_interview_entry(
        db, user_id=user_id, application_id=application_id,
        round=req.round, interview_type=req.interview_type, scheduled_at=req.scheduled_at,
        interviewer=req.interviewer, status=req.status, result=req.result, note=req.note,
    )


@router.put("/interviews/{interview_id}")
def update_interview(interview_id: int, req: InterviewUpdateIn, db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user_id)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    return svc.update_interview_entry(
        db, user_id=user_id, interview_id=interview_id, **fields
    )


@router.delete("/interviews/{interview_id}")
def delete_interview(interview_id: int, db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user_id)):
    return svc.delete_interview_entry(db, user_id=user_id, interview_id=interview_id)
