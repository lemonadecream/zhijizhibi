"""Phase 4 Preparation workspace models.

These tables close the loop from Phase 3 (``capability_gap`` is the SINGLE source
of truth for "what's missing") into "how do I close it":

  * ``prep_plan``        -- one preparation plan per ``target_job`` (+ ``match_id``
                            snapshot so a stale plan can be detected after a
                            recompute / JD reparse).
  * ``prep_task``        -- individual, user-editable preparation actions derived
                            from gaps. User edits are protected on regenerate.
  * ``interview_focus``  -- F14 AI-generated likely interview questions, each bound
                            to a JD requirement + a real user experience.
  * ``resume_advice``    -- F13 AI-generated resume tweaks for this target job.

Design rules (per PRD V0.2 + Phase 4 纪律):
  * Nothing here re-judges a gap or recomputes a match -- it only CONSUMES
    ``target_job`` / ``match_result`` / ``capability_gap`` / ``career_profile``.
  * Every table carries ``user_id`` + index; FKs cascade to the owner so
    cross-user reads are structurally impossible.
  * ``prep_plan`` / ``interview_focus`` / ``resume_advice`` are unique per
    (user, target_job); one workspace per job, switching jobs switches content.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrepPlan(Base):
    """A user's preparation plan for one Target Job.

    Bound to ``target_job_id`` (one plan per job) and snapshots ``match_id`` so
    the program can flag it ``stale`` when the underlying match is recomputed or
    the JD is reparsed. ``overall_progress`` is program-computed (done tasks /
    total). AI never writes a number here.
    """

    __tablename__ = "prep_plan"
    __table_args__ = (
        UniqueConstraint("user_id", "target_job_id", name="uq_user_target_prep"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_job_id: Mapped[int] = mapped_column(
        ForeignKey("target_job.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Snapshot of the match this plan was generated from (for staleness).
    match_id: Mapped[int] = mapped_column(
        ForeignKey("match_result.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Stable signature of the match + gaps this plan was built against. Used to
    # flag the plan ``stale`` when the underlying match is recomputed / JD reparsed
    # (match.id is upserted and stable, so id alone can't detect a recompute).
    match_snapshot: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # empty -> generating -> ready -> editing -> completed; stale is derived.
    status: Mapped[str] = mapped_column(String(12), default="empty", nullable=False, index=True)
    # Program-computed 0..100 (done tasks / total). Never authored by AI.
    overall_progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # P0-1 transparency: ok = real AI authored the advice; fallback = deterministic
    # template. Lets the Prepare plan surface whether advice came from the real
    # provider or the graceful fallback. Additive, non-breaking.
    ai_status: Mapped[str] = mapped_column(String(12), default="ok", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class PrepTask(Base):
    """A single preparation action inside a PrepPlan.

    Derived from a ``capability_gap`` (``gap_id``), but fully editable by the
    user. ``is_user_edited`` protects the task's human-authored fields from being
    overwritten when the plan is regenerated from refreshed gaps.
    """

    __tablename__ = "prep_task"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_id", "ability", name="uq_plan_ability_task"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("prep_plan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Source gap this task addresses (nullable so a manually-added task has none).
    gap_id: Mapped[int | None] = mapped_column(
        ForeignKey("capability_gap.id", ondelete="SET NULL"), index=True, nullable=True
    )

    ability: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # AI-authored explanation (f12): why prepare + how.
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    current_situation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    action_suggestion: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Effective priority (program-owned until the user overrides it).
    priority: Mapped[str] = mapped_column(String(8), default="medium", nullable=False)
    user_priority_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # pending | done (program-owned state; user toggles it).
    status: Mapped[str] = mapped_column(String(8), default="pending", nullable=False)
    user_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # True once the user edits human fields -> protects them on regenerate.
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class InterviewFocus(Base):
    """F14 AI-generated likely interview question for a Target Job.

    Each item is bound to a JD requirement and, where possible, a real user
    experience so the advice is grounded (not generic "interview trivia").

    NOTE: there are intentionally MANY rows per (user, target_job) -- one per
    predicted question -- so NO unique constraint on (user_id, target_job_id).
    """

    __tablename__ = "interview_focus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_job_id: Mapped[int] = mapped_column(
        ForeignKey("target_job.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("match_result.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_snapshot: Mapped[str] = mapped_column(Text, default="", nullable=False)

    question: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_requirement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_experience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    preparation_advice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # sufficient | insufficient | none (does the user have evidence to answer?).
    evidence_status: Mapped[str] = mapped_column(String(12), default="none", nullable=False)
    ai_status: Mapped[str] = mapped_column(String(12), default="ok", nullable=False)

    order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ResumeAdvice(Base):
    """F13 AI-generated resume tweak for a Target Job (P1, lightweight).

    Not a full ATS / resume editor -- just targeted suggestions about which
    experiences to highlight, where evidence is thin, which JD keywords to echo,
    and which weak links to handle honestly.

    NOTE: there are intentionally MANY rows per (user, target_job) -- one per
    suggestion -- so NO unique constraint on (user_id, target_job_id).
    """

    __tablename__ = "resume_advice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_job_id: Mapped[int] = mapped_column(
        ForeignKey("target_job.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("match_result.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_snapshot: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # highlight | evidence_gap | keyword | weak_link
    advice_type: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_experience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_gap: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # high | medium | low
    severity: Mapped[str] = mapped_column(String(8), default="medium", nullable=False)
    ai_status: Mapped[str] = mapped_column(String(12), default="ok", nullable=False)

    order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
