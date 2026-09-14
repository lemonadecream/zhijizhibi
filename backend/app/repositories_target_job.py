"""Repository layer for Target Job (Phase 3).

All direct DB access for the Target Job workspace (target_job / match_result /
capability_gap) lives here so services stay free of ORM details and persistence
is testable. Every query is bound to ``user_id`` -- cross-user reads are
structurally impossible because of the FK + index and the filters below.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.target_job import CapabilityGap, MatchResult, TargetJob


# ----------------------------- target_job -----------------------------
def get_target_job(db: Session, user_id: int, target_job_id: int) -> TargetJob | None:
    return db.scalar(
        select(TargetJob).where(TargetJob.user_id == user_id, TargetJob.id == target_job_id)
    )


def get_target_jobs(db: Session, user_id: int) -> list[TargetJob]:
    return list(
        db.scalars(
            select(TargetJob)
            .where(TargetJob.user_id == user_id)
            .order_by(TargetJob.updated_at.desc())
        ).all()
    )


def get_latest_target_job(db: Session, user_id: int) -> TargetJob | None:
    return db.scalar(
        select(TargetJob)
        .where(TargetJob.user_id == user_id)
        .order_by(TargetJob.updated_at.desc())
    )


def create_target_job(db: Session, *, user_id: int, **fields) -> TargetJob:
    tj = TargetJob(user_id=user_id, **fields)
    db.add(tj)
    db.flush()
    return tj


def update_target_job(db: Session, tj: TargetJob, **fields) -> TargetJob:
    for k, v in fields.items():
        setattr(tj, k, v)
    db.flush()
    return tj


def delete_target_job(db: Session, tj: TargetJob) -> None:
    db.delete(tj)
    db.flush()


# ----------------------------- match_result -----------------------------
def get_match_result(db: Session, user_id: int, target_job_id: int) -> MatchResult | None:
    return db.scalar(
        select(MatchResult).where(
            MatchResult.user_id == user_id, MatchResult.target_job_id == target_job_id
        )
    )


def save_match_result(db: Session, *, user_id: int, target_job_id: int, **fields) -> MatchResult:
    existing = get_match_result(db, user_id, target_job_id)
    if existing is None:
        existing = MatchResult(user_id=user_id, target_job_id=target_job_id, **fields)
        db.add(existing)
    else:
        for k, v in fields.items():
            setattr(existing, k, v)
    db.flush()
    return existing


# ----------------------------- capability_gap -----------------------------
def get_gaps_by_match(db: Session, user_id: int, match_id: int) -> list[CapabilityGap]:
    return list(
        db.scalars(
            select(CapabilityGap)
            .where(CapabilityGap.user_id == user_id, CapabilityGap.match_id == match_id)
            .order_by(CapabilityGap.gap_degree.desc())
        ).all()
    )


def replace_gaps(db: Session, *, user_id: int, match_id: int, gaps: list[dict]) -> list[CapabilityGap]:
    """Replace all gaps for a match (idempotent recompute)."""
    db.query(CapabilityGap).filter(
        CapabilityGap.user_id == user_id, CapabilityGap.match_id == match_id
    ).delete()
    created: list[CapabilityGap] = []
    for g in gaps:
        gap = CapabilityGap(user_id=user_id, match_id=match_id, **g)
        db.add(gap)
        created.append(gap)
    db.flush()
    return created


def get_gap(db: Session, user_id: int, gap_id: int) -> CapabilityGap | None:
    return db.scalar(select(CapabilityGap).where(CapabilityGap.user_id == user_id, CapabilityGap.id == gap_id))
