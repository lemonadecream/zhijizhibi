"""Phase 2 Explore schema migration.

Adds the career knowledge base (industry / job / direction) and the per-user
exploration state (direction_recommendation / explore_state).

The knowledge base tables start EMPTY; their rows are seeded by
``app/services/explore_seed.py`` (idempotent) so the app has real, interrelated
data to recommend against without any external AI call.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers explore tables on Base.metadata)

VERSION = "0003"
NAME = "explore_schema"

REQUIRED_TABLES = {
    "industry",
    "job",
    "direction",
    "direction_recommendation",
    "explore_state",
}


def upgrade(eng):
    Base.metadata.create_all(eng)

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(
            f"Migration {VERSION} failed: missing tables {sorted(missing)}"
        )
