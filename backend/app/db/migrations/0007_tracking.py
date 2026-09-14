"""Phase 5 Tracking workspace migration (F15 投递记录 / F16 面试记录).

Adds the two tables that turn ``/tracking`` into a lightweight job-search
progress center -- NOT an ATS, NOT a recruiting CRM:

  * ``application`` -- one job application the user made (or plans to make),
    with a small status machine and an auto-generated ``timeline`` (JSONB).
  * ``interview``   -- one interview round belonging to an application. Its
    ``result`` links back into the application's status machine (programmatic).

Idempotent: re-running is a no-op once the tables exist. Supports SQLite and
PostgreSQL. Every table carries ``user_id`` + index for isolation; FKs cascade
to the owner so cross-user reads are structurally impossible.

``application.timeline`` is the SINGLE source of truth for status history;
interview events are synthesized into the timeline at read time (no separate
event table, no double-write).
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers tracking tables on Base.metadata)

VERSION = "0007"
NAME = "tracking"

REQUIRED_TABLES = {"application", "interview"}


def upgrade(eng):
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())

    if REQUIRED_TABLES.issubset(existing):
        return  # already applied (idempotent)

    # Create just the new tables (leave 0001-0006 untouched).
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in REQUIRED_TABLES])

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Migration {VERSION} failed: missing tables {sorted(missing)}")
