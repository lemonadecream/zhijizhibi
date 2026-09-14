"""P0-1 transparency: add ai_status column to prep_plan.

Lets the Prepare plan surface whether its AI-generated advice came from the
real provider (ok) or the deterministic fallback (fallback). Additive,
nullable-with-default, non-breaking -- no existing columns or semantics change.

Idempotent: re-running is a no-op once the column exists. SQLite/PG compatible.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

VERSION = "0010"
NAME = "prep_plan_ai_status"


def upgrade(conn):
    """``conn`` is a Connection bound to the runner's single migration
    transaction (see app.db.migrate) -- execute DDL directly on it."""
    inspector = inspect(conn)
    try:
        cols = {c["name"] for c in inspector.get_columns("prep_plan")}
    except Exception:  # noqa: BLE001 -- table may not exist in odd states
        cols = set()

    if "ai_status" in cols:
        return  # already applied (idempotent)

    conn.execute(
        text("ALTER TABLE prep_plan ADD COLUMN ai_status VARCHAR(12) NOT NULL DEFAULT 'ok'")
    )
