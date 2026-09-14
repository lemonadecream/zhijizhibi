"""Offer workspace API (Phase 6: F17-F24).

All endpoints are user-scoped (get_current_user_id). The program owns every
computed number (salary after-tax, disposable, composite, rank); the gateway is
the only AI entry point and its output is only qualitative / explanatory.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user_id
from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.services import analysis_service, cost_service, offer_service
from app.services.decision_service import get_weights

router = APIRouter(prefix="/offer", tags=["offer"])


def _uid() -> int:  # placeholder replaced below
    raise RuntimeError("use Depends(get_current_user_id)")


# ----------------------------- F17/F18: offer CRUD -----------------------------
@router.post("/applications")
def create_offer(payload: dict, user_id: int = Depends(get_current_user_id)):
    try:
        return offer_service.create_offer_entry(
            db=_db(), user_id=user_id,
            company=payload.get("company"),
            job_title=payload.get("job_title"),
            city=payload.get("city"),
            industry=payload.get("industry"),
            work_location=payload.get("work_location"),
            start_date=payload.get("start_date"),
            salary=payload.get("salary"),
            insurance_base=payload.get("insurance_base"),
            fund_rate=payload.get("fund_rate"),
            special_deduction=payload.get("special_deduction", 0),
            benefits=payload.get("benefits"),
            note=payload.get("note", ""),
            status=payload.get("status", "draft"),
            application_id=payload.get("application_id"),
            target_job_id=payload.get("target_job_id"),
        )
    except TypeError:
        raise AppValidationError("请求参数格式不正确", code="invalid_payload")


@router.get("/applications")
def list_offers(status: str | None = Query(None), user_id: int = Depends(get_current_user_id)):
    return offer_service.list_offers(_db(), user_id=user_id, status=status)


@router.get("/applications/{offer_id}")
def get_offer(offer_id: int, user_id: int = Depends(get_current_user_id)):
    return offer_service.get_offer_detail(_db(), user_id=user_id, offer_id=offer_id)


@router.put("/applications/{offer_id}")
def update_offer(offer_id: int, payload: dict, user_id: int = Depends(get_current_user_id)):
    return offer_service.update_offer_entry(_db(), user_id=user_id, offer_id=offer_id, **payload)


@router.delete("/applications/{offer_id}")
def delete_offer(offer_id: int, user_id: int = Depends(get_current_user_id)):
    return offer_service.delete_offer_entry(_db(), user_id=user_id, offer_id=offer_id)


@router.post("/applications/{offer_id}/accept")
def accept_offer(offer_id: int, user_id: int = Depends(get_current_user_id)):
    return offer_service.mark_accepted(_db(), user_id=user_id, offer_id=offer_id)


# ----------------------------- F19: salary after-tax -----------------------------
@router.post("/applications/{offer_id}/salary_calc")
def salary_calc(offer_id: int, payload: dict | None = None,
                user_id: int = Depends(get_current_user_id)):
    """Compute (and persist) the after-tax salary for an offer. All params may be
    overridden per-request; persisted offer values are used as defaults."""
    from app.services.salary_service import build_param_snapshot, compute_salary
    from app.repositories_offer import get_offer, upsert_salary_calc
    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        offer = get_offer(db, user_id, offer_id)
        if offer is None:
            raise AppValidationError("Offer 不存在", code="not_found")
        salary = payload or {}
        offer_salary = {
            "monthly_base": salary.get("monthly_base", (offer.salary or {}).get("monthly_base", 0)),
            "annual_bonus_months": salary.get("annual_bonus_months", (offer.salary or {}).get("annual_bonus_months", 0)),
            "sign_on": salary.get("sign_on", (offer.salary or {}).get("sign_on", 0)),
            "equity_value": salary.get("equity_value", (offer.salary or {}).get("equity_value", 0)),
        }
        city = salary.get("city", offer.city)
        insurance_base = salary.get("insurance_base", offer.insurance_base)
        fund_rate = salary.get("fund_rate", offer.fund_rate)
        special = salary.get("special_deduction", offer.special_deduction)
        results = compute_salary(offer_salary, city=city, insurance_base=insurance_base,
                                 fund_rate=fund_rate, special_deduction=special)
        snap = build_param_snapshot(offer_salary, city=city, insurance_base=insurance_base,
                                    fund_rate=fund_rate, special_deduction=special)
        upsert_salary_calc(db, offer_id=offer_id, city=city, param_snapshot=snap,
                           results=results, tax_version=results["tax_version"],
                           policy_version=results["policy_version"])
        db.commit()
        return {"offer_id": offer_id, "city": city, "results": results, "param_snapshot": snap}
    finally:
        db.close()


# ----------------------------- F20: city cost -----------------------------
@router.get("/cities")
def cities(user_id: int = Depends(get_current_user_id)):
    db = _db()
    return {"cities": cost_service.list_available_cities(db), "user_overrides": _user_overrides(db, user_id)}


def _user_overrides(db, user_id: int) -> list[dict]:
    from app.repositories_offer import get_user_city_cost
    from sqlalchemy import select
    from app.models.offer import UserCityCost
    rows = db.scalars(select(UserCityCost).where(UserCityCost.user_id == user_id)).all()
    return [{"city": r.city, "rent": r.rent, "food": r.food, "transport": r.transport, "misc": r.misc}
            for r in rows]


@router.put("/cities/{city}")
def update_city(city: str, payload: dict, user_id: int = Depends(get_current_user_id)):
    return cost_service.save_user_city_cost(
        _db(), user_id=user_id, city=city,
        rent=payload.get("rent"), food=payload.get("food"),
        transport=payload.get("transport"), misc=payload.get("misc"),
    )


# ----------------------------- F21: qualitative assessment -----------------------------
@router.post("/applications/{offer_id}/assess")
def assess_offer(offer_id: int, payload: dict | None = None,
                 user_id: int = Depends(get_current_user_id)):
    public_signals = (payload or {}).get("public_signals", [])
    user_notes = (payload or {}).get("user_notes", "")
    return analysis_service.run_dimension_assessment(
        _db(), user_id=user_id, offer_id=offer_id,
        public_signals=public_signals, user_notes=user_notes,
    )


# ----------------------------- F22/F23/F24: comparison + analysis -----------------------------
@router.get("/comparison")
def comparison(offer_ids: str | None = Query(None),
               user_id: int = Depends(get_current_user_id)):
    ids = None
    if offer_ids:
        try:
            ids = [int(x) for x in offer_ids.split(",") if x.strip()]
        except ValueError:
            raise AppValidationError("offer_ids 格式错误", code="invalid_param")
    comp = analysis_service.run_decision_analysis(
        _db(), user_id=user_id, offer_ids=ids, extra_context="",
    )
    return comp


@router.get("/weights")
def weights(user_id: int = Depends(get_current_user_id)):
    return get_weights(_db(), user_id=user_id)


@router.put("/weights")
def save_weights(payload: dict, user_id: int = Depends(get_current_user_id)):
    from app.services.decision_service import save_weights
    return save_weights(_db(), user_id=user_id,
                        weights=payload.get("weights", {}),
                        preset_name=payload.get("preset_name"))


def _db():
    from app.db.base import SessionLocal
    return SessionLocal()
