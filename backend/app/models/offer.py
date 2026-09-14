"""Phase 6 Offer Decision workspace models (F17-F24).

This turns ``/offer`` into the final "Offer Decision Workbench" -- the place
where the user answers: how much do I actually take home, what's left after
living costs, how do the non-economic factors compare, and which Offer fits my
weights best. The AI only explains; the program owns every number.

Design rules (per PRD V0.2 + Phase 6 纪律):
  * Pure program logic for ALL numbers (salary, tax, cost, score). AI never
    computes or emits amounts / scores / ranks.
  * Every table carries ``user_id`` + index; FKs cascade to the owner so
    cross-user reads are structurally impossible.
  * ``offer`` is an INDEPENDENT entity. ``application_id`` / ``target_job_id``
    are nullable, read-only weak links (no back-write to upstream phases).
  * ``offer.timeline`` is the SINGLE source of truth for status history.
  * No comparison table: ``comparison_id`` is a batch UUID generated at score
    time (kept in ``score_result`` / ``decision_analysis``), staying lightweight.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------- offer (F17/F18) -----------------------------
class Offer(Base):
    """A user's job offer -- the core of the Offer Decision Workbench (F17).

    Independent entity. Weak links to ``application`` / ``target_job`` are
    optional and read-only (the Offer never writes back to Phase 3/5 rows).
    """

    __tablename__ = "offer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # --- core info ---
    company: Mapped[str] = mapped_column(String(120), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # --- salary structure (JSON; F19 reads from here) ---
    # {monthly_base, annual_bonus_months, sign_on, equity_value}
    #   monthly_base        : 月薪（税前，元）
    #   annual_bonus_months : 年终奖月数（如 2.0 = 2个月工资）；0 表示无年终奖
    #   sign_on             : 签字费（一次性，不进经常性收入，仅展示）
    #   equity_value        : 股票/期权估值（一次性，不进经常性收入，仅展示）
    salary: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)

    # --- insurance inputs (nullable; F19 clamps to city policy) ---
    insurance_base: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 五险一金缴费基数（元/月）
    fund_rate: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )  # 公积金比例（如 0.07 = 7%）；null -> city default

    # --- special additional deduction (专项附加扣除, 月, 元) ---
    # MVP: user-entered total only (no itemized breakdown). Default 0.
    special_deduction: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- benefits / other (JSON list of strings) ---
    benefits: Mapped[list] = mapped_column(JSONCol, default=list, nullable=False)

    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # --- status machine (F18) ---
    # draft -> active -> accepted / rejected / expired
    # Per user decision: marking accepted does NOT auto-reject others
    # (kept as a soft hint only; see services/offer_service.py).
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)

    # --- weak links (read-only; nullable) ---
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.id", ondelete="SET NULL"), index=True, nullable=True
    )
    target_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("target_job.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Status-change event stream (SINGLE source of truth).
    timeline: Mapped[list] = mapped_column(JSONCol, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# ----------------------------- salary_calc (F19 snapshot) -----------------------------
class SalaryCalc(Base):
    """Deterministic salary-calc result snapshot for an Offer (F19).

    Stored so the user can review exactly how the after-tax number was derived
    (transparency + reproducibility). Pure program output.
    """

    __tablename__ = "salary_calc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offer.id", ondelete="CASCADE"), index=True, nullable=False
    )
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # param_snapshot: the FULL input set used (base, insurance_base, fund_rate,
    # special_deduction, tax_version, policy_version) -> reproducible.
    param_snapshot: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    # results: {insurance[], taxable_monthly, monthly_tax, monthly_after_tax,
    #           annual_bonus_after_tax, annual_after_tax, tax_version, policy_version}
    results: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    tax_version: Mapped[str] = mapped_column(String(16), default="2024", nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), default="2024", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ----------------------------- city_cost (seed) + user_city_cost (F20) -----------------------------
class CityCost(Base):
    """Reference monthly living-cost seed for high-frequency cities (F20).

    Pre-seeded, read-only reference data. Source is explicitly "参考数据，非实时".
    """

    __tablename__ = "city_cost"

    city: Mapped[str] = mapped_column(String(80), primary_key=True)
    rent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    food: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transport: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    misc: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_version: Mapped[str] = mapped_column(String(16), default="2024", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="参考", nullable=False)


class UserCityCost(Base):
    """User override of a city's living cost (F20). Per-item nullable.

    Null items fall back to the ``city_cost`` seed.
    """

    __tablename__ = "user_city_cost"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    city: Mapped[str] = mapped_column(String(80), primary_key=True)
    rent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    food: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transport: Mapped[int | None] = mapped_column(Integer, nullable=True)
    misc: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ----------------------------- offer_dimension (F21) + ai_dimension_reference -----------------------------
class OfferDimension(Base):
    """User-confirmed non-economic dimension score for an Offer (F21).

    Four fixed dimensions: workload / stability / growth / match.
    ``score`` (0-100) is ALWAYS user/match-derived -- never AI. AI only writes
    ``ai_dimension_reference`` (judgement tier, no number).
    """

    __tablename__ = "offer_dimension"

    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offer.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(16), primary_key=True)  # workload|stability|growth|match
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 0-100, user/match
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="user", nullable=False)  # user|match
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class AiDimensionReference(Base):
    """AI qualitative reference for a dimension (F21). NEVER enters scoring.

    AI emits a judgement TIER (较高/一般/偏低/信息不足) + evidence + info_source.
    It must NOT emit any numeric score (validated + intercepted at the gateway).
    """

    __tablename__ = "ai_dimension_reference"

    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offer.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(16), primary_key=True)
    judgement: Mapped[str] = mapped_column(String(16), default="信息不足", nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_source: Mapped[str] = mapped_column(String(16), default="user_input", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ----------------------------- decision_weight (F22) -----------------------------
class DecisionWeight(Base):
    """User's comparison weights (F22). Relative weights, no normalization needed.

    One row per user (upsert). ``weights`` JSON keyed by dimension:
      economic | disposable | workload | stability | growth | match
    """

    __tablename__ = "decision_weight"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    weights: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    preset_name: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# ----------------------------- score_result (F23 snapshot) + decision_analysis (F24) -----------------------------
class ScoreResult(Base):
    """A comparison snapshot: one row per offer in a scored batch (F23).

    ``comparison_id`` is a batch UUID (not a FK to a comparison table). Captures
    the composite score + per-dimension scores + weight snapshot at score time,
    so historical decisions stay auditable.
    """

    __tablename__ = "score_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comparison_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offer.id", ondelete="CASCADE"), index=True, nullable=False
    )
    composite_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_snapshot: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    calc_version: Mapped[str] = mapped_column(String(16), default="2024", nullable=False)


class DecisionAnalysis(Base):
    """AI decision analysis for a comparison batch (F24). AI explains only.

    ``content_json`` is the validated AI output (comparison_summary / per_offer
    / sensitivity_notes / conditional_advice / disclaimer). ``data_snapshot`` is
    the program-injected numbers the AI was allowed to reference.
    """

    __tablename__ = "decision_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comparison_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_json: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    data_snapshot: Mapped[dict] = mapped_column(JSONCol, default=dict, nullable=False)
    model_version: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
