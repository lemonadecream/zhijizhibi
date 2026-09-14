"""Manual experience entry service (no AI)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import save_manual_experiences


def save_manual(db: Session, *, user_id: int, parsed: dict) -> None:
    save_manual_experiences(db, user_id, parsed)
