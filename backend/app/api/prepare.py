"""Preparation API routes (Phase 4).

Endpoints (all under /api/prepare, user-isolated via JWT):
  GET    /home                 -> aggregate page state (target/match/gaps/plan/tasks/interview/resume + stale)
  POST   /generate             -> F12 generate preparation plan from gaps (consumes Phase 3)
  PUT    /task/{id}            -> update one prep task (status / priority / note / human fields)
  POST   /interview            -> F14 generate interview focus
  GET    /interview            -> read interview focus
  POST   /resume               -> F13 generate resume advice
  GET    /resume               -> read resume advice

All routes enforce current_user isolation (target_job ownership is re-checked in
the service layer). AI failures degrade per the service layer; no raw crashes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.services import prep_service
from app.repositories_prepare import get_target_job_for_user, get_latest_target_job

router = APIRouter(prefix="/prepare", tags=["prepare"])


# ----------------------------- request models -----------------------------
class GenerateIn(BaseModel):
    target_job_id: int


class TaskUpdateIn(BaseModel):
    status: str | None = None  # pending | done
    priority: str | None = None  # high | medium | low
    user_note: str | None = None
    title: str | None = None
    reason: str | None = None
    action_suggestion: str | None = None


def _resolve_target_job_id(db: Session, user_id: int, target_job_id: int | None) -> int:
    """Use the supplied (owned) target job, else the user's latest one."""
    if target_job_id:
        tj = get_target_job_for_user(db, user_id, target_job_id)
        if tj is None:
            from app.errors.exceptions import NotFoundError as _NF
            raise _NF("目标岗位不存在或不属于当前用户")
        return target_job_id
    latest = get_latest_target_job(db, user_id)
    if latest is None:
        from app.errors.exceptions import ValidationError_ as _VE
        raise _VE("还没有目标岗位，请先在目标岗位工作区建立岗位", code="no_target")
    return latest.id


# ----------------------------- routes -----------------------------
@router.get("/home")
def get_home(target_job_id: int | None = Query(default=None),
             db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    tjid = _resolve_target_job_id(db, user_id, target_job_id) if target_job_id else None
    # When no explicit id, get_prep_home falls back to latest automatically.
    return prep_service.get_prep_home(db, user_id=user_id, target_job_id=tjid)


@router.post("/generate")
def post_generate(req: GenerateIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return prep_service.generate_prep_plan(db, user_id=user_id, target_job_id=req.target_job_id)


@router.post("/battle-plan/{target_job_id}")
def post_battle_plan(target_job_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """备战 Agent：一键编排 匹配→Gap→准备计划→面试重点→简历建议。

    返回完整备战包 + 每步 trace（步骤/耗时）。要求 JD 已确认（user_edited），
    重复调用即全量重算（幂等）。
    """
    from app.services import agent_service

    return agent_service.build_battle_plan(db, user_id=user_id, target_job_id=target_job_id)


@router.put("/task/{task_id}")
def put_task(task_id: int, req: TaskUpdateIn, db: Session = Depends(get_db),
             user_id: int = Depends(get_current_user_id)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    return prep_service.update_prep_task(db, user_id=user_id, task_id=task_id, **fields)


@router.post("/interview")
def post_interview(req: GenerateIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return prep_service.generate_interview_focus(db, user_id=user_id, target_job_id=req.target_job_id)


@router.get("/interview")
def get_interview(target_job_id: int | None = Query(default=None),
                 db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    tjid = _resolve_target_job_id(db, user_id, target_job_id)
    return prep_service.get_interview_focus_list(db, user_id=user_id, target_job_id=tjid)


@router.post("/resume")
def post_resume(req: GenerateIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return prep_service.generate_resume_advice(db, user_id=user_id, target_job_id=req.target_job_id)


@router.get("/resume")
def get_resume(target_job_id: int | None = Query(default=None),
              db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    tjid = _resolve_target_job_id(db, user_id, target_job_id)
    return prep_service.get_resume_advice_list(db, user_id=user_id, target_job_id=tjid)
