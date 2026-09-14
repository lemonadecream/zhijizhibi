"""Repository layer for the onboarding interview session (Phase 1B)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.onboarding import CareerInterviewSession


def get_session(db: Session, user_id: int) -> CareerInterviewSession | None:
    return db.scalar(
        select(CareerInterviewSession).where(CareerInterviewSession.user_id == user_id)
    )


def create_or_get_session(
    db: Session,
    *,
    user_id: int,
    entry_method: str | None = None,
    resume_id: int | None = None,
) -> CareerInterviewSession:
    s = get_session(db, user_id)
    if s is None:
        s = CareerInterviewSession(user_id=user_id)
        db.add(s)
    if entry_method:
        s.entry_method = entry_method
    if resume_id is not None:
        s.resume_id = resume_id
    if s.status == "created":
        s.status = "in_progress"
    db.commit()
    db.refresh(s)
    return s


def save_session(db: Session, s: CareerInterviewSession) -> CareerInterviewSession:
    db.commit()
    db.refresh(s)
    return s


def record_entry_experiences(db: Session, s: CareerInterviewSession, experiences: list[dict]) -> None:
    s.experiences_snapshot = experiences
    if s.status == "created":
        s.status = "in_progress"
    save_session(db, s)


def append_turn(db: Session, s: CareerInterviewSession, role: str, text: str) -> None:
    from datetime import datetime, timezone

    s.question_history = [
        *s.question_history,
        {"role": role, "text": text, "ts": datetime.now(timezone.utc).isoformat()},
    ]
    save_session(db, s)


def update_interview_state(
    db: Session,
    s: CareerInterviewSession,
    *,
    understanding: dict,
    wants_to_know: list,
    dimension_state: list,
    completion_ready: bool = False,
    summary_candidate: str = "",
) -> None:
    s.understanding = understanding
    s.wants_to_know = wants_to_know
    s.dimension_state = dimension_state
    if completion_ready:
        s.summary_pending = {
            "ready": True,
            "summary": summary_candidate,
        }
        s.status = "completed"
    save_session(db, s)


def record_correction(
    db: Session,
    s: CareerInterviewSession,
    *,
    dimension: str,
    from_text: str,
    to_text: str,
) -> None:
    from datetime import datetime, timezone

    s.corrections = [
        *s.corrections,
        {
            "dimension": dimension,
            "from": from_text,
            "to": to_text,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    ]
    save_session(db, s)


def mark_finalized(db: Session, s: CareerInterviewSession) -> None:
    s.status = "finalized"
    save_session(db, s)
