"""Explore domain models (Phase 2).

These tables hold the *structured career knowledge base* (seeded offline / by
admin) and the *per-user exploration process state*.

Design notes (per Phase 2 方案):
  * ``industry`` / ``job`` / ``direction`` are the shared knowledge base. Their
    content is authored/imported, NOT generated at runtime by AI (AI only writes
    ``reason`` text; see F4). This keeps recommendations explainable + offline.
  * ``direction_recommendation`` is the per-user scored candidate set produced by
    the program's deterministic algorithm (not AI).
  * ``explore_state`` is the single row per user holding exploration preferences,
    excluded directions, candidate (saved) directions and the compare set. It is
    what makes refresh-restore + user-isolation work without polluting
    ``work_preference`` (which stays the "job-seeking preference" semantics).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
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


class Industry(Base):
    """Knowledge base: an industry sector (e.g. 互联网 / 金融 / 制造业)."""

    __tablename__ = "industry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Program-readable tags used by the recommender (e.g. ["高成长","技术密集"]).
    traits: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Typical work styles observed in this industry, for compare view.
    work_styles: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Job(Base):
    """Knowledge base: a concrete job role (e.g. 后端工程师 / 产品经理).

    Belongs to an industry; several jobs may map to one direction.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    industry_id: Mapped[int] = mapped_column(
        ForeignKey("industry.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Required abilities (program-readable), matched against user ability_tags.
    required_abilities: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Typical entry barrier 1-5 (program-computed display only; not a score).
    entry_barrier: Mapped[int] = mapped_column(SmallInteger, default=3, nullable=False)
    # Common work style tags.
    work_styles: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Direction(Base):
    """Knowledge base: a career *direction* (e.g. 技术专家线 / 产品管理线).

    A direction aggregates several jobs + industries and is the unit the user
    explores & compares. ``match_axes`` are the comparable dimensions surfaced in
    the compare view (program reads them; AI never decides ranking).
    """

    __tablename__ = "direction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # One-line human summary shown on the card.
    summary: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Industry ids this direction spans.
    industry_ids: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Job ids commonly associated with this direction.
    job_ids: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Core abilities this direction leverages (matched vs user ability_tags).
    core_abilities: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Work styles typical of this direction (e.g. ["独立钻研","团队协作"]).
    work_styles: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Program-readable attributes used by the deterministic recommender.
    # e.g. {"growth":0.8,"stability":0.4,"autonomy":0.7,"social":0.5}
    # These are KNOWLEDGE-BASE values, NOT user scores.
    attributes: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)
    # What this direction is NOT great at (honest counter-point on the card).
    not_good_for: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Development path (text), shown in compare view.
    growth_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DirectionRecommendation(Base):
    """Per-user, program-scored candidate direction (one row per user×direction).

    Produced by the deterministic recommender. ``score`` and ``match_basis`` are
    computed by the program; ``reason`` is the ONLY AI-authored field (F4),
    degradable to a template when AI is unavailable.
    """

    __tablename__ = "direction_recommendation"
    __table_args__ = (
        UniqueConstraint("user_id", "direction_id", name="uq_user_direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    direction_id: Mapped[int] = mapped_column(
        ForeignKey("direction.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 0..1 program-computed match (NOT an AI judgment).
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    # Human-readable, program-built explanation of WHY this score (deterministic).
    match_basis: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # AI-authored "why this fits you" text (F4). Empty if AI unavailable.
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reason_status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)
    # "active" | "excluded" (user said not interested). Excluded rows are skipped
    # in the UI but kept so re-inclusion / re-compute is possible.
    status: Mapped[str] = mapped_column(String(12), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ExploreState(Base):
    """Single process-state row per user for the Explore workspace.

    Holds the user's exploration preferences (parsed from natural-language input
    by the program), the excluded set, the saved/candidate set and the compare
    set. This is what enables refresh-restore and a clean separation from
    ``work_preference`` (job-seeking preference).
    """

    __tablename__ = "explore_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Structured exploration preferences (program-parsed). e.g.
    # {"prefer_fields":["互联网"], "avoid_keywords":["纯技术"], "prefer_city":"上海",
    #  "value_stability":true, "value_growth":true}
    preferences: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)
    # Direction ids the user explicitly excluded ("不感兴趣").
    excluded_direction_ids: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Direction ids the user saved as candidates ("收藏 / 候选方向").
    candidate_direction_ids: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Direction ids currently selected for comparison (max 4).
    compare_direction_ids: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    # Whether the user has chosen a target direction -> migrated to Target Job.
    target_direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
