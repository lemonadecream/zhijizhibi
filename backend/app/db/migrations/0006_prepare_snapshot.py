"""Phase 4 staleness support migration.

Adds a ``match_snapshot`` TEXT column to ``prep_plan`` / ``interview_focus`` /
``resume_advice``. The snapshot is a stable signature of the match + gaps a
preparation artifact was generated against.

Because ``match_result`` is upserted (the same ``match.id`` is reused across
re-matches), comparing ``match_id`` alone can never detect that the match was
recomputed or the JD was reparsed. The signature lets the program flag
prepared content ``stale`` when the underlying match actually changes.

Idempotent: skips any column that already exists. Uses ADD COLUMN DDL that is
valid on both SQLite and PostgreSQL for a simple NOT NULL TEXT column.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app import models  # noqa: F401  (registers prepare tables on Base.metadata)

VERSION = "0006"
NAME = "prepare_snapshot"

COLUMNS = {
    "prep_plan": ["match_snapshot"],
    "interview_focus": ["match_snapshot"],
    "resume_advice": ["match_snapshot"],
}


def upgrade(conn):
    """``conn`` is a Connection bound to the runner's single migration
    transaction (see app.db.migrate) -- execute DDL directly on it."""
    inspector = inspect(conn)
    for table, cols in COLUMNS.items():
        existing = {c["name"] for c in inspector.get_columns(table)}
        for col in cols:
            if col in existing:
                continue
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            )
