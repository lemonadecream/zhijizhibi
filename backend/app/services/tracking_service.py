"""Tracking service (Phase 5: F15 投递记录 / F16 面试记录).

Owns:
  * The Application status machine (program-owned, no AI).
  * ``application.timeline`` -- the SINGLE source of truth for status history.
    Interview events are synthesized into the timeline at READ time so there is
    no separate event table and no double-write.
  * Interview lifecycle + result -> application status linkage:
      interview.result == "pass" => application.status = offer_received
      interview.result == "fail" => application.status = rejected
      (manual override is always possible afterwards)
  * The Tracking overview (counts, upcoming interviews, recent activity).

Design rules (per PRD V0.2 + Phase 5 纪律):
  * Pure program logic -- no AI, no external services.
  * Every mutation commits (get_db does not auto-commit; cross-request
    consumers need durable rows).
  * All calls are user-scoped; repositories re-check ownership.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.models.tracking import Application, Interview
from app.repositories_tracking import (
    create_application,
    create_interview,
    delete_application,
    delete_interview,
    get_application,
    get_applications,
    get_interview,
    get_interviews,
    get_upcoming_interviews,
    update_application,
    update_interview,
)

# ----------------------------- status machine -----------------------------
# Allowed Application statuses (F15):
#   drafted -> applied -> written_test -> interviewing -> (terminal) offer_received / rejected / withdrawn
_VALID_STATUSES = {
    "drafted", "applied", "written_test", "interviewing",
    "offer_received", "rejected", "withdrawn",
}

# Terminal states cannot be left (manual reopen is out of scope for Phase 5).
_TERMINAL = {"offer_received", "rejected", "withdrawn"}

# Allowed transitions (explicit allow-list; everything else is rejected).
_ALLOWED_TRANSITIONS = {
    "drafted": {"applied", "withdrawn"},
    "applied": {"written_test", "interviewing", "rejected", "withdrawn", "offer_received"},
    "written_test": {"interviewing", "rejected", "withdrawn", "offer_received"},
    "interviewing": {"offer_received", "rejected", "withdrawn"},
    "offer_received": set(),
    "rejected": set(),
    "withdrawn": set(),
}

_STATUS_LABELS = {
    "drafted": "草稿",
    "applied": "已投递",
    "written_test": "笔试中",
    "interviewing": "面试中",
    "offer_received": "已拿 Offer",
    "rejected": "未通过",
    "withdrawn": "已放弃",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_status(value: str, *, field: str = "status") -> str:
    if value not in _VALID_STATUSES:
        raise AppValidationError(
            f"非法的{field}：{value!r}", code="invalid_status"
        )
    return value


def _transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, set())


def _append_timeline(app: Application, *, to_status: str, note: str | None = None) -> None:
    """Append a status-change event (the SINGLE source of truth)."""
    ev = {
        "status": to_status,
        "from_status": app.status,
        "ts": _now().isoformat(),

    }
    if note:
        ev["note"] = note
    timeline = list(app.timeline or [])
    timeline.append(ev)
    app.timeline = timeline


# ----------------------------- application CRUD -----------------------------
def create_application_entry(
    db: Session, *, user_id: int, company: str, job_title: str,
    city: str | None = None, job_url: str | None = None, source: str | None = None,
    applied_at: str | None = None, status: str = "drafted",
    next_action: str | None = None, next_action_at: str | None = None,
    note: str = "", target_job_id: int | None = None,
) -> dict:
    company = (company or "").strip()
    job_title = (job_title or "").strip()
    if not company or not job_title:
        raise AppValidationError("公司名称与岗位名称均必填", code="missing_fields")
    _ensure_status(status)

    applied_date = _parse_date(applied_at) if applied_at else None
    next_at = _parse_date(next_action_at) if next_action_at else None

    app = create_application(
        db, user_id=user_id,
        company=company, job_title=job_title, city=city, job_url=job_url, source=source,
        applied_at=applied_date, status=status,
        next_action=next_action, next_action_at=next_at,
        note=note or "", target_job_id=target_job_id,
    )
    # Seed the timeline with the creation event.
    _append_timeline(app, to_status=status)
    db.commit()
    db.refresh(app)
    return _app_to_dict(app)


def list_applications(db: Session, *, user_id: int, status: str | None = None) -> dict:
    apps = get_applications(db, user_id, status=status)
    return {
        "items": [_app_to_dict(a) for a in apps],
        "total": len(apps),
    }


def get_application_detail(db: Session, *, user_id: int, application_id: int) -> dict:
    app = get_application(db, user_id, application_id)
    if app is None:
        raise NotFoundError("投递记录不存在")
    interviews = get_interviews(db, user_id, application_id=app.id)
    return {
        "application": _app_to_dict(app),
        "interviews": [_iv_to_dict(iv) for iv in interviews],
        # Timeline + interview events merged at read time (SINGLE source of truth).
        "timeline": _merged_timeline(app, interviews),
    }


def update_application_entry(
    db: Session, *, user_id: int, application_id: int,
    company: str | None = None, job_title: str | None = None, city: str | None = None,
    job_url: str | None = None, source: str | None = None, applied_at: str | None = None,
    status: str | None = None, next_action: str | None = None,
    next_action_at: str | None = None, note: str | None = None,
    target_job_id: int | None = None,
) -> dict:
    app = get_application(db, user_id, application_id)
    if app is None:
        raise NotFoundError("投递记录不存在")

    # Status change: validate the transition then record it in the timeline.
    if status is not None and status != app.status:
        _ensure_status(status)
        if app.status in _TERMINAL:
            raise AppValidationError(
                f"当前状态「{_STATUS_LABELS.get(app.status, app.status)}」为终态，无法再变更",
                code="terminal_status",
            )
        if not _transition_allowed(app.status, status):
            raise AppValidationError(
                f"不允许的状态流转：{_STATUS_LABELS.get(app.status, app.status)} → "
                f"{_STATUS_LABELS.get(status, status)}",
                code="illegal_transition",
            )
        # Record the transition in the timeline BEFORE mutating status, so the
        # event's from_status reflects the old value.
        _append_timeline(app, to_status=status)
        app.status = status

    # Plain field updates (never blindly overwrite note; caller decides).
    if company is not None:
        app.company = company.strip()
    if job_title is not None:
        app.job_title = job_title.strip()
    if city is not None:
        app.city = city
    if job_url is not None:
        app.job_url = job_url
    if source is not None:
        app.source = source
    if applied_at is not None:
        app.applied_at = _parse_date(applied_at) if applied_at else None
    if next_action is not None:
        app.next_action = next_action
    if next_action_at is not None:
        app.next_action_at = _parse_date(next_action_at) if next_action_at else None
    if note is not None:
        app.note = note
    if target_job_id is not None:
        app.target_job_id = target_job_id

    db.commit()
    db.refresh(app)
    return _app_to_dict(app)


def delete_application_entry(db: Session, *, user_id: int, application_id: int) -> dict:
    app = get_application(db, user_id, application_id)
    if app is None:
        raise NotFoundError("投递记录不存在")
    delete_application(db, app)
    db.commit()
    return {"deleted": True}


# ----------------------------- interview CRUD -----------------------------
def create_interview_entry(
    db: Session, *, user_id: int, application_id: int,
    round: str | None = None, interview_type: str | None = None,
    scheduled_at: str | None = None, interviewer: str | None = None,
    status: str = "scheduled", result: str = "pending", note: str | None = None,
) -> dict:
    app = get_application(db, user_id, application_id)
    if app is None:
        raise NotFoundError("投递记录不存在，无法添加面试")

    if status not in {"scheduled", "completed", "cancelled"}:
        raise AppValidationError("非法的面试状态", code="invalid_interview_status")
    if result not in {"pending", "pass", "fail"}:
        raise AppValidationError("非法的面试结果", code="invalid_interview_result")

    sched = _parse_datetime(scheduled_at) if scheduled_at else None
    iv = create_interview(
        db, user_id=user_id, application_id=application_id,
        round=round, interview_type=interview_type, scheduled_at=sched,
        interviewer=interviewer, status=status, result=result, note=note,
    )
    db.commit()
    db.refresh(iv)
    return _iv_to_dict(iv)


def update_interview_entry(
    db: Session, *, user_id: int, interview_id: int,
    round: str | None = None, interview_type: str | None = None,
    scheduled_at: str | None = None, status: str | None = None,
    result: str | None = None, interviewer: str | None = None, note: str | None = None,
) -> dict:
    iv = get_interview(db, user_id, interview_id)
    if iv is None:
        raise NotFoundError("面试记录不存在")

    if status is not None and status not in {"scheduled", "completed", "cancelled"}:
        raise AppValidationError("非法的面试状态", code="invalid_interview_status")
    if result is not None and result not in {"pending", "pass", "fail"}:
        raise AppValidationError("非法的面试结果", code="invalid_interview_result")

    if round is not None:
        iv.round = round
    if interview_type is not None:
        iv.interview_type = interview_type
    if scheduled_at is not None:
        iv.scheduled_at = _parse_datetime(scheduled_at) if scheduled_at else None
    if status is not None:
        iv.status = status
    if interviewer is not None:
        iv.interviewer = interviewer
    if note is not None:
        iv.note = note

    # Result linkage: pass/fail drive the application status machine.
    if result is not None and result != iv.result:
        iv.result = result
        _apply_interview_result(db, iv, result)

    db.commit()
    db.refresh(iv)
    return _iv_to_dict(iv)


def delete_interview_entry(db: Session, *, user_id: int, interview_id: int) -> dict:
    iv = get_interview(db, user_id, interview_id)
    if iv is None:
        raise NotFoundError("面试记录不存在")
    delete_interview(db, iv)
    db.commit()
    return {"deleted": True}


def _apply_interview_result(db: Session, iv: Interview, result: str) -> None:
    """Program linkage: interview result -> application status machine.

    Per PRD + user decision:
      * pass  -> offer_received (only if not already terminal)
      * fail  -> rejected       (only if not already terminal)
      * pending -> no change
    Manual override afterwards is always possible (this is a convenience push).
    """
    app = get_application(db, iv.user_id, iv.application_id)
    if app is None or app.status in _TERMINAL:
        return
    target = "offer_received" if result == "pass" else "rejected" if result == "fail" else None
    if target is None or not _transition_allowed(app.status, target):
        return
    app.status = target
    _append_timeline(app, to_status=target, note=f"面试结果：{'通过' if result == 'pass' else '未通过'}")


# ----------------------------- overview -----------------------------
def get_tracking_overview(db: Session, *, user_id: int) -> dict:
    apps = get_applications(db, user_id)
    upcoming = get_upcoming_interviews(db, user_id)

    counts: dict[str, int] = {s: 0 for s in _VALID_STATUSES}
    for a in apps:
        counts[a.status] = counts.get(a.status, 0) + 1

    return {
        "total": len(apps),
        "counts": counts,
        "counts_labeled": {_STATUS_LABELS.get(k, k): v for k, v in counts.items() if v},
        "upcoming_interviews": [_iv_to_dict(iv) for iv in upcoming],
        "recent": [_app_to_dict(a) for a in apps[:5]],
    }


# ----------------------------- helpers -----------------------------
def _parse_date(value: str) -> date:
    """Accept YYYY-MM-DD (or datetime); return a date."""
    if "T" in value or " " in value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.date()
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    """Accept ISO datetime (with or without timezone)."""
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _merged_timeline(app: Application, interviews: list[Interview]) -> list[dict]:
    """SINGLE source of truth: application status events + synthesized interview
    events, sorted by time descending for display."""
    events: list[dict] = []

    for ev in (app.timeline or []):
        events.append({
            "kind": "status",
            "status": ev.get("status"),
            "from_status": ev.get("from_status"),
            "ts": ev.get("ts"),
            "note": ev.get("note"),
        })

    for iv in interviews:
        if iv.scheduled_at:
            events.append({
                "kind": "interview",
                "interview_id": iv.id,
                "round": iv.round,
                "interview_type": iv.interview_type,
                "result": iv.result,
                "ts": iv.scheduled_at.isoformat(),
                "note": iv.note,
            })

    def _sort_key(e: dict):
        ts = e.get("ts") or ""
        return ts

    events.sort(key=_sort_key, reverse=True)
    return events


def _app_to_dict(app: Application) -> dict:
    return {
        "application_id": app.id,
        "user_id": app.user_id,
        "target_job_id": app.target_job_id,
        "company": app.company,
        "job_title": app.job_title,
        "city": app.city,
        "job_url": app.job_url,
        "source": app.source,
        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        "status": app.status,
        "status_label": _STATUS_LABELS.get(app.status, app.status),
        "next_action": app.next_action,
        "next_action_at": app.next_action_at.isoformat() if app.next_action_at else None,
        "note": app.note or "",
        "timeline": app.timeline or [],
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


def _iv_to_dict(iv: Interview) -> dict:
    return {
        "interview_id": iv.id,
        "application_id": iv.application_id,
        "user_id": iv.user_id,
        "round": iv.round,
        "interview_type": iv.interview_type,
        "scheduled_at": iv.scheduled_at.isoformat() if iv.scheduled_at else None,
        "status": iv.status,
        "interviewer": iv.interviewer,
        "result": iv.result,
        "note": iv.note,
        "created_at": iv.created_at.isoformat() if iv.created_at else None,
        "updated_at": iv.updated_at.isoformat() if iv.updated_at else None,
    }
