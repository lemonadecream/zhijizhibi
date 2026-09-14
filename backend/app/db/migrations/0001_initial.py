"""Initial schema migration.

Creates every table declared on ``Base.metadata``. Keeping the schema in a
versioned migration (rather than relying on ``create_all`` scattered through
the app) makes the schema explicit and replayable.

On SQLite the TIMESTAMP column works without DEFAULT support; the
``schema_migrations`` table already handles applied-version tracking.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base

# Importing the models package registers every ORM table on ``Base.metadata``.
# This guarantees the tables exist even when this migration is run standalone
# (e.g. in a unit test) before any router/service has imported them.
from app import models  # noqa: F401

VERSION = "0001"
NAME = "initial_schema"

# Tables that MUST exist after this migration runs. Used as a sanity guard so
# a partial failure surfaces loudly instead of silently shipping an incomplete
# schema.
REQUIRED_TABLES = {
    "users",
    "user_profile",
    "education_exp",
    "internship_exp",
    "project_exp",
    "skill",
    "interest",
    "work_preference",
    "career_goal",
    "resume",
    "career_profile",
    "profile_revision_log",
}


def upgrade(eng):
    """Create all tables and verify the required ones exist."""
    Base.metadata.create_all(eng)

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(
            f"Migration {VERSION} failed: missing tables {sorted(missing)}"
        )
