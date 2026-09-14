"""Phase 6 Offer Decision workspace migration -- Part 1 (F17/F18/F19/F20/F21).

Adds the core Offer tables + F19/F20/F21 data layer:
  * ``offer``                  -- independent Offer entity (F17/F18)
  * ``salary_calc``            -- F19 deterministic after-tax snapshot
  * ``city_cost``              -- F20 reference living-cost seed (10 high-freq cities)
  * ``user_city_cost``         -- F20 user override
  * ``offer_dimension``        -- F21 user/match dimension score (0-100)
  * ``ai_dimension_reference`` -- F21 AI qualitative reference (no number)

Idempotent: re-running is a no-op once the tables exist. SQLite/PG compatible.
Every table carries ``user_id`` + index (where applicable) for isolation.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app import models  # noqa: F401  (registers offer tables on Base.metadata)
from app.db.seed_city_cost import seed_city_costs

VERSION = "0008"
NAME = "offer"

REQUIRED_TABLES = {
    "offer", "salary_calc", "city_cost", "user_city_cost",
    "offer_dimension", "ai_dimension_reference",
}

# Reference monthly living-cost seed (元/月). Source: 参考数据，非实时.
# rent / food / transport / misc. Values are reasonable 2024-era estimates for
# a single fresh graduate; the user can override via user_city_cost.
_CITY_SEED = {
    "北京": dict(rent=3500, food=1800, transport=400, misc=1200),
    "上海": dict(rent=3200, food=1800, transport=400, misc=1200),
    "广州": dict(rent=2200, food=1500, transport=300, misc=900),
    "深圳": dict(rent=3000, food=1700, transport=400, misc=1100),
    "杭州": dict(rent=2500, food=1500, transport=350, misc=900),
    "成都": dict(rent=1800, food=1300, transport=300, misc=800),
    "武汉": dict(rent=1600, food=1200, transport=300, misc=700),
    "南京": dict(rent=2000, food=1400, transport=300, misc=800),
    "西安": dict(rent=1500, food=1200, transport=300, misc=700),
    "苏州": dict(rent=1900, food=1400, transport=300, misc=800),
}


def upgrade(eng):
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())

    if REQUIRED_TABLES.issubset(existing):
        seed_city_costs(eng)  # ensure seed rows exist even on re-run
        return  # already applied (idempotent)

    # Create just the new tables (leave 0001-0007 untouched).
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in REQUIRED_TABLES])

    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Migration {VERSION} failed: missing tables {sorted(missing)}")

    seed_city_costs(eng)


def _seed_cities(eng, *, force: bool) -> None:
    """Kept for backwards compatibility; prefer ``app.db.seed_city_cost``."""
    seed_city_costs(eng)
