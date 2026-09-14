"""City living-cost service (F20) -- pure, deterministic.

Computes monthly / annual living cost for a city + the resulting disposable
income from a (program-computed) monthly after-tax salary. All numbers are
program-owned; the AI never touches them.

Data model:
  * ``city_cost`` (seed)      -- reference rent/food/transport/misc for 10 cities
  * ``user_city_cost`` (override) -- per-item user override; null falls back to seed

Monthly living cost = rent + food + transport + misc (each resolved: user override
else seed). Disposable monthly = monthly_after_tax - monthly_cost.
"""
from __future__ import annotations

from app.repositories_offer import (
    get_city_cost,
    get_user_city_cost,
    list_city_costs,
    upsert_user_city_cost,
)


def _resolve_item(seed_val: int, user_val: int | None) -> int:
    return user_val if user_val is not None else seed_val


def resolve_city_cost(db, *, user_id: int, city: str | None) -> dict:
    """Resolve effective monthly cost for a city (user override > seed > zeros).

    Returns {city, rent, food, transport, misc, monthly_total, source}.
    """
    if not city:
        return {
            "city": None, "rent": 0, "food": 0, "transport": 0, "misc": 0,
            "monthly_total": 0, "source": "none",
        }
    seed = get_city_cost(db, city)
    user = get_user_city_cost(db, user_id, city)

    seed_rent = seed.rent if seed else 0
    seed_food = seed.food if seed else 0
    seed_transport = seed.transport if seed else 0
    seed_misc = seed.misc if seed else 0

    rent = _resolve_item(seed_rent, user.rent if user else None)
    food = _resolve_item(seed_food, user.food if user else None)
    transport = _resolve_item(seed_transport, user.transport if user else None)
    misc = _resolve_item(seed_misc, user.misc if user else None)

    total = rent + food + transport + misc
    source = "user_override" if user else ("seed" if seed else "none")
    return {
        "city": city, "rent": rent, "food": food,
        "transport": transport, "misc": misc,
        "monthly_total": total, "source": source,
    }


def compute_disposable(monthly_after_tax: float, monthly_cost: int) -> dict:
    """Disposable income from after-tax salary minus living cost."""
    monthly = float(monthly_after_tax) - float(monthly_cost)
    return {
        "monthly_disposable": round(monthly + 1e-9, 2),
        "annual_disposable": round(monthly * 12 + 1e-9, 2),
    }


def save_user_city_cost(db, *, user_id: int, city: str,
                        rent: int | None, food: int | None,
                        transport: int | None, misc: int | None) -> dict:
    """Persist a user city-cost override (per-item nullable)."""
    if not city:
        raise ValueError("city is required")
    row = upsert_user_city_cost(
        db, user_id=user_id, city=city,
        rent=rent, food=food, transport=transport, misc=misc,
    )
    db.commit()
    return {
        "user_id": row.user_id, "city": row.city,
        "rent": row.rent, "food": row.food,
        "transport": row.transport, "misc": row.misc,
    }


def list_available_cities(db) -> list[dict]:
    """Return all seed cities (for the UI picker)."""
    rows = list_city_costs(db)
    return [
        {
            "city": r.city, "rent": r.rent, "food": r.food,
            "transport": r.transport, "misc": r.misc,
            "data_version": r.data_version, "source": r.source,
        }
        for r in rows
    ]
