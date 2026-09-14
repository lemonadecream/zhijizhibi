"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.db.base import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    # Lightweight liveness; connectivity to DB is verified separately at startup.
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "db": "down", "detail": str(exc)}
