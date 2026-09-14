"""F20 reference living-cost seed (元/月) for 10 high-frequency cities.

Reference data, not real-time. A fresh graduate's monthly rent / food /
transport / misc. The user can override any city via ``user_city_cost``.

Extracted so both the migration and the app lifespan can keep the seed present
(e.g. tests truncate tables between runs).
"""
from __future__ import annotations

from sqlalchemy import text

# rent / food / transport / misc (元/月). 2024-era reasonable estimates.
CITY_SEED = {
    "北京": dict(rent=3500, food=1800, transport=400, misc=1200),
    "上海": dict(rent= 3200, food=1800, transport=400, misc=1200),
    "广州": dict(rent=2200, food=1500, transport=300, misc=900),
    "深圳": dict(rent=3000, food=1700, transport=400, misc=1100),
    "杭州": dict(rent=2500, food=1500, transport=350, misc=900),
    "成都": dict(rent=1800, food=1300, transport=300, misc=800),
    "武汉": dict(rent=1600, food=1200, transport=300, misc=700),
    "南京": dict(rent=2000, food=1400, transport=300, misc=800),
    "西安": dict(rent=1500, food=1200, transport=300, misc=700),
    "苏州": dict(rent=1900, food=1400, transport=300, misc=800),
}


def seed_city_costs(eng) -> int:
    """Insert reference city-cost rows. Idempotent: skips existing cities.

    Returns the number of rows inserted. ``eng`` may be an Engine or a
    Connection: the migration runner passes a Connection bound to the
    migration's transaction, the app lifespan passes the engine.
    """
    if hasattr(eng, "execute"):  # Connection: use it directly, commit is the caller's
        return _seed(eng)

    with eng.connect() as conn:
        n = _seed(conn)
        conn.commit()
        return n


def _seed(conn) -> int:
    rows = conn.execute(text("SELECT city FROM city_cost")).fetchall()
    have = {r[0] for r in rows}
    to_insert = []
    for city, vals in CITY_SEED.items():
        if city in have:
            continue
        to_insert.append({
            "city": city,
            "rent": vals["rent"],
            "food": vals["food"],
            "transport": vals["transport"],
            "misc": vals["misc"],
            "data_version": "2024",
            "source": "参考",
        })
    if to_insert:
        conn.execute(text(
            "INSERT INTO city_cost (city, rent, food, transport, misc, data_version, source) "
            "VALUES (:city, :rent, :food, :transport, :misc, :data_version, :source)"
        ), to_insert)
    return len(to_insert)
