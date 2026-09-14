"""Phase 6 Offer Decision workspace migration -- Part 2 (F22/F23/F24).

Adds the decision-comparison data layer:
  * ``decision_weight``    -- F22 user comparison weights (relative, no norm)
  * ``score_result``       -- F23 deterministic composite-score snapshot
  * ``decision_analysis``  -- F24 AI qualitative analysis (explains only)

Idempotent: re-running is a no-op once the tables exist. SQLite/PG compatible.
Every table carries ``user_id`` + index (where applicable) for isolation.

Note: no ``comparison`` table. ``comparison_id`` is a batch UUID generated at
score time, stored on ``score_result`` / ``decision_analysis``. This keeps the
schema lightweight per the "don't add tables just to be complete" rule.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers decision tables on Base.metadata)

VERSION = "0009"
NAME = "decision"

REQUIRED_TABLES = {"decision_weight", "score_result", "decision_analysis"}


def upgrade(eng):
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())

    if REQUIRED_TABLES.issubset(existing):
        return  # already applied (idempotent)

    # Create just the new tables (leave 0001-0008 untouched).
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in REQUIRED_TABLES])

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Migration {VERSION} failed: missing tables {sorted(missing)}")
