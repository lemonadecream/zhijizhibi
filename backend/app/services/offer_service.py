"""Offer workspace service (Phase 6: F17 录入 / F18 状态管理).

Owns:
  * Offer CRUD (create / update / delete) with optional weak links
    (application_id / target_job_id) -- read-only, never back-writes upstream.
  * The Offer status machine (program-owned, no AI).
  * ``offer.timeline`` -- SINGLE source of truth for status history.

Per user decision (Phase 6 拍板):
  * accepted does NOT auto-reject other offers. We keep others as-is and only
    surface a soft hint in the API response. No silent state mutation.

Design rules:
  * Pure program logic -- no AI, no external services.
  * All calls are user-scoped; repositories re-check ownership.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.models.offer import Offer
from app.repositories_offer import (
    create_offer,
    delete_offer,
    get_offer,
    get_offers,
    update_offer,
)

# ----------------------------- status machine (F18) -----------------------------
# draft -> active -> accepted / rejected / expired
# Per decision: accepted does NOT cascade to others. Each offer is independent.
_VALID_STATUSES = {"draft", "active", "accepted", "rejected", "expired"}

_TERMINAL = {"accepted", "rejected", "expired"}

_ALLOWED_TRANSITIONS = {
    "draft": {"active", "rejected", "expired"},
    "active": {"accepted", "rejected", "expired", "draft"},
    "accepted": set(),   # terminal; cannot leave (no reopen in MVP)
    "rejected": set(),   # terminal
    "expired": {"draft"},  # can re-activate an expired draft
}

_STATUS_LABELS = {
    "draft": "草稿",
    "active": "进行中",
    "accepted": "已接受",
    "rejected": "已放弃",
    "expired": "已过期",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_status(value: str) -> str:
    if value not in _VALID_STATUSES:
        raise AppValidationError(f"非法的 Offer 状态：{value!r}", code="invalid_status")
    return value


def _transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, set())


def _append_timeline(offer: Offer, *, to_status: str, note: str | None = None) -> None:
    ev = {"status": to_status, "from_status": offer.status, "ts": _now().isoformat()}
    if note:
        ev["note"] = note
    timeline = list(offer.timeline or [])
    timeline.append(ev)
    offer.timeline = timeline


def _coerce_salary(salary: dict | None) -> dict:
    if not salary:
        return {}
    allowed = {"monthly_base", "annual_bonus_months", "sign_on", "equity_value"}
    out = {}
    for k in allowed:
        if k in salary and salary[k] is not None:
            out[k] = salary[k]
    return out


# ----------------------------- CRUD -----------------------------
def create_offer_entry(
    db: Session, *, user_id: int,
    company: str, job_title: str, city: str | None = None,
    industry: str | None = None, work_location: str | None = None,
    start_date: str | None = None, salary: dict | None = None,
    insurance_base: int | None = None, fund_rate: float | None = None,
    special_deduction: int = 0, benefits: list | None = None, note: str = "",
    status: str = "draft", application_id: int | None = None,
    target_job_id: int | None = None,
) -> dict:
    company = (company or "").strip()
    job_title = (job_title or "").strip()
    if not company or not job_title:
        raise AppValidationError("公司名称与岗位名称均必填", code="missing_fields")
    _ensure_status(status)

    offer = create_offer(
        db, user_id=user_id,
        company=company, job_title=job_title, city=city, industry=industry,
        work_location=work_location,
        start_date=_parse_date(start_date) if start_date else None,
        salary=_coerce_salary(salary), insurance_base=insurance_base,
        fund_rate=fund_rate, special_deduction=int(special_deduction or 0),
        benefits=benefits or [], note=note or "",
        status=status, application_id=application_id, target_job_id=target_job_id,
    )
    _append_timeline(offer, to_status=status)
    db.commit()
    db.refresh(offer)
    return _offer_to_dict(offer)


def list_offers(db: Session, *, user_id: int, status: str | None = None) -> dict:
    offers = get_offers(db, user_id, status=status)
    return {"items": [_offer_to_dict(o) for o in offers], "total": len(offers)}


def get_offer_detail(db: Session, *, user_id: int, offer_id: int) -> dict:
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise NotFoundError("Offer 不存在")
    return _offer_to_dict(offer)


def update_offer_entry(
    db: Session, *, user_id: int, offer_id: int, **fields
) -> dict:
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise NotFoundError("Offer 不存在")

    # Status change (F18): validate transition, record in timeline.
    new_status = fields.pop("status", None)
    if new_status is not None and new_status != offer.status:
        _ensure_status(new_status)
        if offer.status in _TERMINAL:
            raise AppValidationError(
                f"当前状态「{_STATUS_LABELS.get(offer.status, offer.status)}」为终态，无法再变更",
                code="terminal_status",
            )
        if not _transition_allowed(offer.status, new_status):
            raise AppValidationError(
                f"不允许的状态流转：{_STATUS_LABELS.get(offer.status, offer.status)} → "
                f"{_STATUS_LABELS.get(new_status, new_status)}",
                code="illegal_transition",
            )
        _append_timeline(offer, to_status=new_status)
        offer.status = new_status

    # Plain field updates.
    if "company" in fields and fields["company"] is not None:
        offer.company = fields["company"].strip()
    if "job_title" in fields and fields["job_title"] is not None:
        offer.job_title = fields["job_title"].strip()
    if "city" in fields:
        offer.city = fields["city"]
    if "industry" in fields:
        offer.industry = fields["industry"]
    if "work_location" in fields:
        offer.work_location = fields["work_location"]
    if "start_date" in fields and fields["start_date"] is not None:
        offer.start_date = _parse_date(fields["start_date"]) if fields["start_date"] else None
    if "salary" in fields and fields["salary"] is not None:
        offer.salary = _coerce_salary(fields["salary"])
    if "insurance_base" in fields:
        offer.insurance_base = fields["insurance_base"]
    if "fund_rate" in fields:
        offer.fund_rate = fields["fund_rate"]
    if "special_deduction" in fields and fields["special_deduction"] is not None:
        offer.special_deduction = int(fields["special_deduction"] or 0)
    if "benefits" in fields and fields["benefits"] is not None:
        offer.benefits = fields["benefits"] or []
    if "note" in fields:
        offer.note = fields["note"] or ""
    if "application_id" in fields:
        offer.application_id = fields["application_id"]
    if "target_job_id" in fields:
        offer.target_job_id = fields["target_job_id"]

    db.commit()
    db.refresh(offer)
    return _offer_to_dict(offer)


def delete_offer_entry(db: Session, *, user_id: int, offer_id: int) -> dict:
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise NotFoundError("Offer 不存在")
    delete_offer(db, offer)
    db.commit()
    return {"deleted": True}


def mark_accepted(db: Session, *, user_id: int, offer_id: int) -> dict:
    """Mark an offer accepted (F18). Per user decision: does NOT auto-reject
    other offers. Returns a soft hint if the user has other active offers."""
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise NotFoundError("Offer 不存在")
    if offer.status != "accepted":
        if offer.status in _TERMINAL:
            raise AppValidationError(
                f"当前状态「{_STATUS_LABELS.get(offer.status, offer.status)}」为终态，无法标记为已接受",
                code="terminal_status",
            )
        _append_timeline(offer, to_status="accepted", note="标记为我的选择")
        offer.status = "accepted"
        db.commit()
        db.refresh(offer)

    others = [o for o in get_offers(db, user_id, status="active") if o.id != offer.id]
    return {
        **_offer_to_dict(offer),
        "other_active_offers": [_offer_to_dict(o) for o in others],
        "hint": (
            "你还有其他进行中的 Offer，可以自行决定是否调整它们的状态。"
            if others else None
        ),
    }


# ----------------------------- helpers -----------------------------
def _parse_date(value: str):
    from datetime import date, datetime
    if "T" in value or " " in value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.date()
    return date.fromisoformat(value)


def _offer_to_dict(offer: Offer) -> dict:
    return {
        "offer_id": offer.id,
        "user_id": offer.user_id,
        "company": offer.company,
        "industry": offer.industry,
        "job_title": offer.job_title,
        "city": offer.city,
        "work_location": offer.work_location,
        "start_date": offer.start_date.isoformat() if offer.start_date else None,
        "salary": offer.salary or {},
        "insurance_base": offer.insurance_base,
        "fund_rate": float(offer.fund_rate) if offer.fund_rate is not None else None,
        "special_deduction": offer.special_deduction,
        "benefits": offer.benefits or [],
        "note": offer.note or "",
        "status": offer.status,
        "status_label": _STATUS_LABELS.get(offer.status, offer.status),
        "application_id": offer.application_id,
        "target_job_id": offer.target_job_id,
        "timeline": offer.timeline or [],
        "created_at": offer.created_at.isoformat() if offer.created_at else None,
        "updated_at": offer.updated_at.isoformat() if offer.updated_at else None,
    }
