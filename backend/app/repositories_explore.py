"""Repository layer for Explore (Phase 2).

All direct DB access for the Explore workspace lives here so services stay
free of ORM details and the persistence is testable.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.explore import (
    Direction,
    DirectionRecommendation,
    ExploreState,
    Industry,
    Job,
)


# ----------------------------- Knowledge base -----------------------------
def get_all_directions(db: Session) -> list[Direction]:
    return list(db.scalars(select(Direction)).all())


def get_direction(db: Session, direction_id: int) -> Direction | None:
    return db.get(Direction, direction_id)


def get_industries_by_ids(db: Session, ids: list[int]) -> list[Industry]:
    if not ids:
        return []
    return list(db.scalars(select(Industry).where(Industry.id.in_(ids))).all())


def get_jobs_by_ids(db: Session, ids: list[int]) -> list[Job]:
    if not ids:
        return []
    return list(db.scalars(select(Job).where(Job.id.in_(ids))).all())


# ----------------------------- Per-user recommendation -----------------------------
def get_recommendations(db: Session, user_id: int) -> list[DirectionRecommendation]:
    return list(
        db.scalars(
            select(DirectionRecommendation)
            .where(DirectionRecommendation.user_id == user_id)
            .order_by(DirectionRecommendation.score.desc())
        ).all()
    )


def get_recommendation(db: Session, user_id: int, direction_id: int) -> DirectionRecommendation | None:
    return db.scalar(
        select(DirectionRecommendation).where(
            DirectionRecommendation.user_id == user_id,
            DirectionRecommendation.direction_id == direction_id,
        )
    )


def upsert_recommendation(
    db: Session, *, user_id: int, direction_id: int, score: float,
    match_basis: list[str], reason: str = "", reason_status: str = "pending",
) -> DirectionRecommendation:
    rec = get_recommendation(db, user_id, direction_id)
    if rec is None:
        rec = DirectionRecommendation(
            user_id=user_id, direction_id=direction_id, score=score,
            match_basis=match_basis, reason=reason, reason_status=reason_status,
        )
        db.add(rec)
    else:
        rec.score = score
        rec.match_basis = match_basis
        if reason:
            rec.reason = reason
            rec.reason_status = reason_status
    db.flush()
    return rec


def set_recommendation_excluded(db: Session, *, user_id: int, direction_id: int, excluded: bool) -> None:
    rec = get_recommendation(db, user_id, direction_id)
    if rec is not None:
        rec.status = "excluded" if excluded else "active"
        db.flush()


# ----------------------------- Explore state -----------------------------
def get_explore_state(db: Session, user_id: int) -> ExploreState | None:
    return db.get(ExploreState, user_id)


def get_or_create_explore_state(db: Session, user_id: int) -> ExploreState:
    st = db.get(ExploreState, user_id)
    if st is None:
        st = ExploreState(user_id=user_id)
        db.add(st)
        db.flush()
    return st


def save_explore_state(db: Session, st: ExploreState) -> ExploreState:
    db.flush()
    db.commit()
    db.refresh(st)
    return st
