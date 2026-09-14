"""Repository layer for the Tracking workspace (Phase 5: F15 / F16).

All direct DB access for ``/tracking`` (application / interview) lives here so
services stay free of ORM details and persistence is testable. Every query is
bound to ``user_id`` -- cross-user reads are structurally impossible because of
the FK + index and the filters below.

Pure program logic: no AI, no external services.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tracking import Application, Interview


# ----------------------------- application -----------------------------
def get_application(db: Session, user_id: int, application_id: int) -> Application | None:
    return db.scalar(
        select(Application).where(
            Application.user_id == user_id, Application.id == application_id
        )
    )


def get_applications(db: Session, user_id: int, *, status: str | None = None) -> list[Application]:
    stmt = select(Application).where(Application.user_id == user_id)
    if status:
        stmt = stmt.where(Application.status == status)
    stmt = stmt.order_by(Application.created_at.desc())
    return list(db.scalars(stmt).all())


def create_application(db: Session, *, user_id: int, **fields) -> Application:
    app = Application(user_id=user_id, **fields)
    db.add(app)
    db.flush()
    return app


def update_application(db: Session, app: Application, **fields) -> Application:
    for k, v in fields.items():
        setattr(app, k, v)
    db.flush()
    return app


def delete_application(db: Session, app: Application) -> None:
    db.delete(app)
    db.flush()


# ----------------------------- interview -----------------------------
def get_interview(db: Session, user_id: int, interview_id: int) -> Interview | None:
    return db.scalar(
        select(Interview).where(
            Interview.user_id == user_id, Interview.id == interview_id
        )
    )


def get_interviews(db: Session, user_id: int, *, application_id: int | None = None) -> list[Interview]:
    stmt = select(Interview).where(Interview.user_id == user_id)
    if application_id is not None:
        stmt = stmt.where(Interview.application_id == application_id)
    stmt = stmt.order_by(Interview.scheduled_at.asc().nullslast(), Interview.created_at.asc())
    return list(db.scalars(stmt).all())


def get_upcoming_interviews(db: Session, user_id: int) -> list[Interview]:
    """Scheduled interviews with a future-ish schedule, ascending by time."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = (
        select(Interview)
        .where(
            Interview.user_id == user_id,
            Interview.status == "scheduled",
            Interview.scheduled_at.is_not(None),
            Interview.scheduled_at >= now,
        )
        .order_by(Interview.scheduled_at.asc())
    )
    return list(db.scalars(stmt).all())


def create_interview(db: Session, *, user_id: int, application_id: int, **fields) -> Interview:
    iv = Interview(user_id=user_id, application_id=application_id, **fields)
    db.add(iv)
    db.flush()
    return iv


def update_interview(db: Session, iv: Interview, **fields) -> Interview:
    for k, v in fields.items():
        setattr(iv, k, v)
    db.flush()
    return iv


def delete_interview(db: Session, iv: Interview) -> None:
    db.delete(iv)
    db.flush()
