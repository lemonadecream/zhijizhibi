"""Target Job domain models (Phase 3).

These tables hold the per-user, JD-level decision workspace that closes the loop
from "direction" (Phase 2) to "concrete job decision":

  * ``target_job``       -- a user's concrete job target bound to a specific JD
                            (or a job knowledge-base item + custom JD).
  * ``match_result``     -- the program-computed F10 match (score / dimensions /
                            strengths / risks). AI only supplies per-ability
                            relation judgments; the score is program-owned.
  * ``capability_gap``   -- F11 gaps (the single source of truth for Phase 4
                            Prepare). Program computes degree + priority.

Design notes (per Phase 3 方案 + 实施前审查报告):
  * ``target_job`` coexists with ``explore_state.target_direction_id`` (direction
    context) -- it does NOT replace it. It is the JD-level instance.
  * ``job`` (knowledge base) is NOT upgraded; F9's structured ``ability_model``
    lives in ``target_job`` only.
  * ``career_profile`` stays folded; nothing here re-imports its columns.
  * All three tables carry ``user_id`` + index for isolation; deletion cascades
    to the owner so cross-user reads are structurally impossible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
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
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TargetJob(Base):
    """A user's concrete job target (JD-level), bound to a specific JD.

    Unlike ``explore_state.target_direction_id`` (a direction-level context),
    this is a persisted decision object built from a real JD the user pasted or
    selected. ``ability_model`` is the structured output of F9 and is the single
    source of truth for matching (NOT the generic ``job.required_abilities``).
    """

    __tablename__ = "target_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Optional direction context carried over from Explore (NOT a constraint).
    direction_id: Mapped[int | None] = mapped_column(
        ForeignKey("direction.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Optional knowledge-base job used as a prefill source (NOT a constraint).
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("job.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # --- Raw + source metadata (user-supplied) ---
    source_jd: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)  # {"raw_text","parsed_json"}
    job_title: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    company: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    city: Mapped[str] = mapped_column(String(60), default="", nullable=False)

    # --- F9 structured output (the matchable ability model) ---
    # ability_model: {"abilities":[{name,category,level,weight,requirement_type}],
    #                 "requirements":{education,experience_years,major[],cert[]}}
    ability_model: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)
    # Short human overview fields surfaced in the JD summary card.
    industry: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    responsibilities: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    other_requirements: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)

    # --- Lifecycle ---
    # unparsed -> parsing -> parsed -> user_edited -> matched
    jd_status: Mapped[str] = mapped_column(String(16), default="unparsed", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class MatchResult(Base):
    """Program-computed F10 match for a TargetJob.

    The AI (f10_match_judge) ONLY emits per-ability ``relation`` (covered /
    partial / missing) + reason + evidence. The ``total_score``, dimension
    scores, strengths and risks are computed by the program from those
    relations. AI never writes a number here.
    """

    __tablename__ = "match_result"
    __table_args__ = (
        UniqueConstraint("user_id", "target_job_id", name="uq_user_target_match"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_job_id: Mapped[int] = mapped_column(
        ForeignKey("target_job.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Profile + JD version stamps so a stale match can be flagged for recompute.
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jd_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Program-computed (0..100). Never authored by AI.
    total_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Per-dimension scores, e.g. [{"axis":"硬技能","score":0.8}, ...]
    dimension_scores: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    strengths: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    risks: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Full per-ability judgement list (AI relation + program coverage value).
    relation_judgements: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Whether the semantic judgement came from AI or a program fallback.
    ai_status: Mapped[str] = mapped_column(String(12), default="ok", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class CapabilityGap(Base):
    """F11 capability gap (single source of truth for Phase 4 Prepare).

    Program computes ``gap_degree`` (0..1: higher = bigger gap) and ``priority``
    from the match judgement + required level. AI (f11_gap_explain) only writes
    the human explanation (why / evidence / direction_hint).
    """

    __tablename__ = "capability_gap"
    __table_args__ = (
        UniqueConstraint("user_id", "match_id", "ability", name="uq_user_match_gap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("match_result.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ability: Mapped[str] = mapped_column(String(120), nullable=False)
    # Evidence the program / AI found in the user's profile & experiences.
    current_evidence: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    required_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Program-computed 0..1; higher = bigger gap. Never from AI.
    gap_degree: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Program-computed priority for Phase 4 (high / medium / low).
    priority: Mapped[str] = mapped_column(String(8), default="medium", nullable=False)
    # AI-authored explanation (f11). Empty if AI unavailable.
    why: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    improvement_direction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # open / closed (user can mark a gap as addressed -- Phase 4 consumes it).
    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
