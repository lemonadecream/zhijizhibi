"""Phase 3 Target Job schema migration.

Adds the JD-level decision workspace that closes the loop from Explore
(direction) to a concrete job decision:
  * ``target_job``      -- per-user concrete job target bound to a JD
  * ``match_result``    -- program-computed F10 match (AI only judges relations)
  * ``capability_gap``  -- F11 gaps (single source of truth for Phase 4 Prepare)

Idempotent: re-running is a no-op once the tables exist. Supports SQLite and
PostgreSQL (JSONCol auto-degrades). All tables carry ``user_id`` + index for
isolation; FK deletes cascade to the owner so cross-user reads are impossible.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers target_job tables on Base.metadata)

VERSION = "0004"
NAME = "target_job"

REQUIRED_TABLES = {"target_job", "match_result", "capability_gap"}


def upgrade(eng):
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())

    if REQUIRED_TABLES.issubset(existing):
        return  # already applied (idempotent)

    # Create just the new tables (leave 0001-0003 untouched).
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in REQUIRED_TABLES])

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Migration {VERSION} failed: missing tables {sorted(missing)}")
