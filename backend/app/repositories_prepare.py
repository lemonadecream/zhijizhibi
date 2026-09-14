"""Repository layer for the Phase 4 Preparation workspace.

All direct DB access for prep_plan / prep_task / interview_focus / resume_advice
lives here. Every query is bound to ``user_id`` -- cross-user reads are
structurally impossible because of the FK + index and the filters below.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prepare import InterviewFocus, PrepPlan, PrepTask, ResumeAdvice
from app.models.target_job import TargetJob


# ----------------------------- prep_plan -----------------------------
def get_prep_plan(db: Session, user_id: int, target_job_id: int) -> PrepPlan | None:
    return db.scalar(
        select(PrepPlan).where(
            PrepPlan.user_id == user_id, PrepPlan.target_job_id == target_job_id
        )
    )


def get_prep_plan_by_id(db: Session, user_id: int, plan_id: int) -> PrepPlan | None:
    return db.scalar(
        select(PrepPlan).where(PrepPlan.user_id == user_id, PrepPlan.id == plan_id)
    )


def upsert_prep_plan(db: Session, *, user_id: int, target_job_id: int, match_id: int,
                     **fields) -> PrepPlan:
    existing = get_prep_plan(db, user_id, target_job_id)
    if existing is None:
        existing = PrepPlan(
            user_id=user_id, target_job_id=target_job_id, match_id=match_id, **fields
        )
        db.add(existing)
    else:
        existing.match_id = match_id
        for k, v in fields.items():
            setattr(existing, k, v)
    db.flush()
    return existing


# ----------------------------- prep_task -----------------------------
def get_tasks_by_plan(db: Session, user_id: int, plan_id: int) -> list[PrepTask]:
    return list(
        db.scalars(
            select(PrepTask)
            .where(PrepTask.user_id == user_id, PrepTask.plan_id == plan_id)
            .order_by(PrepTask.order.asc(), PrepTask.id.asc())
        ).all()
    )


def get_task(db: Session, user_id: int, task_id: int) -> PrepTask | None:
    return db.scalar(
        select(PrepTask).where(PrepTask.user_id == user_id, PrepTask.id == task_id)
    )


def add_task(db: Session, *, user_id: int, plan_id: int, **fields) -> PrepTask:
    task = PrepTask(user_id=user_id, plan_id=plan_id, **fields)
    db.add(task)
    db.flush()
    return task


def update_task(db: Session, task: PrepTask, **fields) -> PrepTask:
    for k, v in fields.items():
        setattr(task, k, v)
    db.flush()
    return task


def delete_tasks_by_ability(db: Session, *, user_id: int, plan_id: int, abilities: set[str]) -> None:
    """Remove tasks whose ability is no longer present in the refreshed gap set."""
    db.query(PrepTask).filter(
        PrepTask.user_id == user_id,
        PrepTask.plan_id == plan_id,
        PrepTask.ability.notin_(abilities),
    ).delete()


# ----------------------------- interview_focus -----------------------------
def get_interview_focus(db: Session, user_id: int, target_job_id: int) -> list[InterviewFocus]:
    return list(
        db.scalars(
            select(InterviewFocus)
            .where(InterviewFocus.user_id == user_id, InterviewFocus.target_job_id == target_job_id)
            .order_by(InterviewFocus.order.asc(), InterviewFocus.id.asc())
        ).all()
    )


def replace_interview_focus(db: Session, *, user_id: int, target_job_id: int, match_id: int,
                            match_snapshot: str, items: list[dict]) -> list[InterviewFocus]:
    db.query(InterviewFocus).filter(
        InterviewFocus.user_id == user_id, InterviewFocus.target_job_id == target_job_id
    ).delete()
    created: list[InterviewFocus] = []
    for i, it in enumerate(items):
        row = InterviewFocus(
            user_id=user_id, target_job_id=target_job_id, match_id=match_id,
            match_snapshot=match_snapshot, order=i, **it,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


# ----------------------------- resume_advice -----------------------------
def get_resume_advice(db: Session, user_id: int, target_job_id: int) -> list[ResumeAdvice]:
    return list(
        db.scalars(
            select(ResumeAdvice)
            .where(ResumeAdvice.user_id == user_id, ResumeAdvice.target_job_id == target_job_id)
            .order_by(ResumeAdvice.order.asc(), ResumeAdvice.id.asc())
        ).all()
    )


def replace_resume_advice(db: Session, *, user_id: int, target_job_id: int, match_id: int,
                         match_snapshot: str, items: list[dict]) -> list[ResumeAdvice]:
    db.query(ResumeAdvice).filter(
        ResumeAdvice.user_id == user_id, ResumeAdvice.target_job_id == target_job_id
    ).delete()
    created: list[ResumeAdvice] = []
    for i, it in enumerate(items):
        row = ResumeAdvice(
            user_id=user_id, target_job_id=target_job_id, match_id=match_id,
            match_snapshot=match_snapshot, order=i, **it,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


# ----------------------------- target_job lookup (isolation) -----------------------------
def get_target_job_for_user(db: Session, user_id: int, target_job_id: int) -> TargetJob | None:
    return db.scalar(
        select(TargetJob).where(TargetJob.user_id == user_id, TargetJob.id == target_job_id)
    )


def get_latest_target_job(db: Session, user_id: int) -> TargetJob | None:
    return db.scalar(
        select(TargetJob)
        .where(TargetJob.user_id == user_id)
        .order_by(TargetJob.updated_at.desc())
    )
