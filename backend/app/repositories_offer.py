"""Repository layer for the Offer Decision workspace (Phase 6: F17-F24).

All direct DB access for ``/offer`` lives here so services stay free of ORM
details and persistence is testable. Every query is bound to ``user_id`` --
cross-user reads are structurally impossible because of the FK + index and the
filters below.

Pure program logic: no AI, no external services.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.offer import (
    AiDimensionReference,
    CityCost,
    DecisionAnalysis,
    DecisionWeight,
    Offer,
    OfferDimension,
    SalaryCalc,
    ScoreResult,
    UserCityCost,
)


# ----------------------------- offer -----------------------------
def get_offer(db: Session, user_id: int, offer_id: int) -> Offer | None:
    return db.scalar(
        select(Offer).where(Offer.user_id == user_id, Offer.id == offer_id)
    )


def get_offers(db: Session, user_id: int, *, status: str | None = None) -> list[Offer]:
    stmt = select(Offer).where(Offer.user_id == user_id)
    if status:
        stmt = stmt.where(Offer.status == status)
    stmt = stmt.order_by(Offer.created_at.desc())
    return list(db.scalars(stmt).all())


def get_all_offers(db: Session, user_id: int) -> list[Offer]:
    return get_offers(db, user_id)


def create_offer(db: Session, *, user_id: int, **fields) -> Offer:
    offer = Offer(user_id=user_id, **fields)
    db.add(offer)
    db.flush()
    return offer


def update_offer(db: Session, offer: Offer, **fields) -> Offer:
    for k, v in fields.items():
        setattr(offer, k, v)
    db.flush()
    return offer


def delete_offer(db: Session, offer: Offer) -> None:
    db.delete(offer)
    db.flush()


# ----------------------------- salary_calc -----------------------------
def get_salary_calc(db: Session, offer_id: int) -> SalaryCalc | None:
    return db.scalar(
        select(SalaryCalc).where(SalaryCalc.offer_id == offer_id)
        .order_by(SalaryCalc.created_at.desc())
    )


def upsert_salary_calc(db: Session, *, offer_id: int, city: str | None,
                       param_snapshot: dict, results: dict,
                       tax_version: str, policy_version: str) -> SalaryCalc:
    calc = get_salary_calc(db, offer_id)
    if calc is None:
        calc = SalaryCalc(offer_id=offer_id)
        db.add(calc)
    calc.city = city
    calc.param_snapshot = param_snapshot
    calc.results = results
    calc.tax_version = tax_version
    calc.policy_version = policy_version
    db.flush()
    return calc


# ----------------------------- city_cost -----------------------------
def get_city_cost(db: Session, city: str) -> CityCost | None:
    return db.scalar(select(CityCost).where(CityCost.city == city))


def list_city_costs(db: Session) -> list[CityCost]:
    return list(db.scalars(select(CityCost).order_by(CityCost.city)).all())


def get_user_city_cost(db: Session, user_id: int, city: str) -> UserCityCost | None:
    return db.scalar(
        select(UserCityCost).where(UserCityCost.user_id == user_id, UserCityCost.city == city)
    )


def upsert_user_city_cost(db: Session, *, user_id: int, city: str,
                          rent: int | None, food: int | None,
                          transport: int | None, misc: int | None) -> UserCityCost:
    row = get_user_city_cost(db, user_id, city)
    if row is None:
        row = UserCityCost(user_id=user_id, city=city)
        db.add(row)
    if rent is not None:
        row.rent = rent
    if food is not None:
        row.food = food
    if transport is not None:
        row.transport = transport
    if misc is not None:
        row.misc = misc
    db.flush()
    return row


# ----------------------------- offer_dimension + ai_dimension_reference -----------------------------
def get_dimensions(db: Session, offer_id: int) -> list[OfferDimension]:
    return list(db.scalars(
        select(OfferDimension).where(OfferDimension.offer_id == offer_id)
    ).all())


def upsert_dimension(db: Session, *, offer_id: int, dimension: str,
                     score: int | None, evidence: str | None,
                     source: str) -> OfferDimension:
    dim = db.scalar(
        select(OfferDimension).where(
            OfferDimension.offer_id == offer_id, OfferDimension.dimension == dimension
        )
    )
    if dim is None:
        dim = OfferDimension(offer_id=offer_id, dimension=dimension)
        db.add(dim)
    dim.score = score
    if evidence is not None:
        dim.evidence = evidence
    dim.source = source
    db.flush()
    return dim


def get_ai_reference(db: Session, offer_id: int, dimension: str) -> AiDimensionReference | None:
    return db.scalar(
        select(AiDimensionReference).where(
            AiDimensionReference.offer_id == offer_id,
            AiDimensionReference.dimension == dimension,
        )
    )


def upsert_ai_reference(db: Session, *, offer_id: int, dimension: str,
                        judgement: str, evidence: str | None,
                        info_source: str) -> AiDimensionReference:
    ref = get_ai_reference(db, offer_id, dimension)
    if ref is None:
        ref = AiDimensionReference(offer_id=offer_id, dimension=dimension)
        db.add(ref)
    ref.judgement = judgement
    ref.evidence = evidence
    ref.info_source = info_source
    db.flush()
    return ref


# ----------------------------- decision_weight -----------------------------
def get_decision_weight(db: Session, user_id: int) -> DecisionWeight | None:
    return db.scalar(
        select(DecisionWeight).where(DecisionWeight.user_id == user_id)
        .order_by(DecisionWeight.updated_at.desc())
    )


def upsert_decision_weight(db: Session, *, user_id: int, weights: dict,
                           preset_name: str | None) -> DecisionWeight:
    row = get_decision_weight(db, user_id)
    if row is None:
        row = DecisionWeight(user_id=user_id)
        db.add(row)
    row.weights = weights
    row.preset_name = preset_name
    db.flush()
    return row


# ----------------------------- score_result + decision_analysis -----------------------------
def save_score_results(db: Session, *, comparison_id: str,
                       results: list[dict]) -> list[ScoreResult]:
    rows = []
    for r in results:
        row = ScoreResult(
            comparison_id=comparison_id,
            offer_id=r["offer_id"],
            composite_score=r["composite_score"],
            dimension_scores=r["dimension_scores"],
            rank=r["rank"],
            weight_snapshot=r["weight_snapshot"],
        )
        db.add(row)
        db.flush()
        rows.append(row)
    return rows


def get_latest_score_results(db: Session, user_id: int, comparison_id: str) -> list[ScoreResult]:
    # User-scoped: join through offer ownership.
    return list(db.scalars(
        select(ScoreResult)
        .join(Offer, Offer.id == ScoreResult.offer_id)
        .where(Offer.user_id == user_id, ScoreResult.comparison_id == comparison_id)
        .order_by(ScoreResult.rank.asc())
    ).all())


def save_decision_analysis(db: Session, *, comparison_id: str, user_id: int,
                           content_json: dict, data_snapshot: dict,
                           model_version: str) -> DecisionAnalysis:
    row = DecisionAnalysis(
        comparison_id=comparison_id,
        user_id=user_id,
        content_json=content_json,
        data_snapshot=data_snapshot,
        model_version=model_version,
    )
    db.add(row)
    db.flush()
    return row


def get_latest_analysis(db: Session, user_id: int, comparison_id: str) -> DecisionAnalysis | None:
    return db.scalar(
        select(DecisionAnalysis)
        .where(DecisionAnalysis.user_id == user_id,
               DecisionAnalysis.comparison_id == comparison_id)
        .order_by(DecisionAnalysis.created_at.desc())
    )
