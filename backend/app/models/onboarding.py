"""Onboarding interview session -- the single process-data table for Phase 1B.

One row per user. All interview process state lives here:
  * ``dimension_state``: per-dimension (D1..D6) understanding completeness + notes
  * ``understanding``: the AI's progressive "what I know about you" snapshot
  * ``question_history``: the conversational turns (user + ai) for resume/refresh
  * ``wants_to_know``: the AI's open follow-up questions ("我还想了解")
  * ``experiences_snapshot``: confirmed experiences at interview start (context)
  * ``corrections``: user edits to the AI's understanding (editable, not read-only)

The final career_profile is generated separately (F2) and stored in
``career_profile`` -- this table is purely the *process* scratch pad.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CareerInterviewSession(Base):
    __tablename__ = "career_interview_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )

    # Lifecycle: created -> in_progress -> completed -> finalized
    status: Mapped[str] = mapped_column(String(16), default="created", nullable=False)

    # Entry method used to bootstrap this session: upload / paste / scratch
    entry_method: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Linked resume id (if the user uploaded/pasted a resume) -- context only.
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Interview process state (all JSON; dialect-agnostic via JSONCol) ---
    # dimension_state: { "D1": {"covered": true, "confidence": 0.6, "note": "..."}, ... }
    dimension_state: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)

    # understanding: { "tags": [...], "sentences": [...], "evidence": {...} }
    understanding: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)

    # wants_to_know: list of open follow-up prompts the AI still wants to ask.
    wants_to_know: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)

    # question_history: [ {"role": "user"|"ai", "text": "...", "ts": "..."}, ... ]
    question_history: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)

    # corrections: [ {"dimension": "D5", "from": "...", "to": "...", "ts": "..."} ]
    corrections: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)

    # experiences_snapshot captured when the interview (or scratch) began.
    experiences_snapshot: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)

    summary_pending: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
