"""Phase 5 Tracking workspace models (F15 投递记录 / F16 面试记录).

These tables turn ``/tracking`` into a lightweight "job-search progress center"
for the user -- NOT an ATS, NOT a recruiting CRM:

  * ``application`` -- one job application the user has made (or plans to make),
    with a small status machine and an auto-generated ``timeline`` (JSONB).
  * ``interview``   -- one interview round belonging to an application. Its
    ``result`` links back into the application's status machine (programmatic).

Design rules (per PRD V0.2 + Phase 5 纪律):
  * Pure program logic -- no AI, no external services.
  * Every table carries ``user_id`` + index; FKs cascade to the owner so
    cross-user reads are structurally impossible.
  * ``application.timeline`` is the SINGLE source of truth for status history;
    interview events are synthesized into the timeline at read time (no
    separate event table, no double-write).
  * ``target_job_id`` is a nullable FK: applications may come from a Target Job
    (pre-filled) or be recorded manually.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Application(Base):
    """A user's job application (or planned application) -- the core of F15."""

    __tablename__ = "application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Optional link back to a Target Job (Phase 3). Null for manual entries.
    target_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("target_job.id", ondelete="SET NULL"), index=True, nullable=True
    )

    company: Mapped[str] = mapped_column(String(120), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Channel: 内推 / 招聘网站 / 官网 / 其他 (optional, used for filtering).
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)

    applied_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    # Status machine (see services/tracking_service.py).
    status: Mapped[str] = mapped_column(String(16), default="drafted", nullable=False, index=True)

    # Lightweight "next step" reminder (single, not a task manager).
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Free-form notes; appended via the service (never overwritten blindly).
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Status-change event stream [{status, from_status, ts, note?}]. The SINGLE
    # source of truth for history; interview events are merged in at read time.
    timeline: Mapped[list] = mapped_column(JSONCol, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class Interview(Base):
    """One interview round for an Application (F16)."""

    __tablename__ = "interview"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Round label: 一面 / 二面 / 三面 / HR面 / 笔试 / 其他 (free text).
    round: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Type: 技术 / HR / 主管 / 笔试 (optional, richer than round).
    interview_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Drives the "upcoming interviews" module.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Lifecycle: scheduled | completed | cancelled.
    status: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)
    interviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Result: pass | fail | pending. pass/fail link back to application status.
    result: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    # Free-form self-notes: questions asked / how it went / what to improve next.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
