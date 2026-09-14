"""Phase 4 Preparation workspace migration.

Adds the four tables that turn Phase 3's gaps into an actionable preparation
plan + interview/resume advice:
  * ``prep_plan``        -- one plan per (user, target_job), snapshots match_id
  * ``prep_task``        -- user-editable preparation actions from gaps
  * ``interview_focus``  -- F14 likely questions (per target_job)
  * ``resume_advice``    -- F13 resume tweaks (per target_job)

Idempotent: re-running is a no-op once the tables exist. Supports SQLite and
PostgreSQL (all scalar/Text columns -- no JSON here). Every table carries
``user_id`` + index for isolation; FKs cascade to the owner.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers prepare tables on Base.metadata)

VERSION = "0005"
NAME = "prepare"

REQUIRED_TABLES = {"prep_plan", "prep_task", "interview_focus", "resume_advice"}


def upgrade(eng):
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())

    if REQUIRED_TABLES.issubset(existing):
        return  # already applied (idempotent)

    # Create just the new tables (leave 0001-0004 untouched).
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in REQUIRED_TABLES])

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Migration {VERSION} failed: missing tables {sorted(missing)}")
