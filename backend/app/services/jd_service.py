"""JD service (Phase 3 Target Job).

Owns the F9 JD lifecycle:
  * create a target_job (from Explore direction or blank)
  * run F9 parse on a raw JD (AI; degrades to a program fallback)
  * let the user view / edit / confirm the structured result
  * persist the confirmed ability_model (never overwritten by AI)

Principles (per PRD + 方案):
  * AI only writes the structured parse; the user's confirmed edit is the truth.
  * All failures degrade gracefully so JD creation works with no API key.
  * No scores / salary / verdicts are emitted by the AI.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError, get_gateway
from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.repositories_target_job import (
    create_target_job,
    delete_target_job,
    get_latest_target_job,
    get_target_job,
    get_target_jobs,
    update_target_job,
)
from app.services.explore_service import _unfold_profile  # reuse profile unfolding


# ----------------------------- create / list -----------------------------
def create_target_job_entry(
    db: Session, *, user_id: int, direction_id: int | None = None, job_id: int | None = None,
    job_title: str = "", company: str = "", city: str = "", raw_jd: str = "",
) -> dict:
    """Create a new (empty) target_job row. JD is parsed later via parse_jd."""
    if raw_jd and len(raw_jd.strip()) < 10:
        raise AppValidationError("JD 内容过短，请粘贴完整的岗位描述", code="jd_too_short")
    tj = create_target_job(
        db, user_id=user_id,
        direction_id=direction_id, job_id=job_id,
        job_title=job_title or "", company=company or "", city=city or "",
        source_jd={"raw_text": raw_jd or "", "parsed_json": {}},
        ability_model={}, industry="", responsibilities=[], other_requirements=[],
        jd_status="unparsed",
    )
    db.commit()
    db.refresh(tj)
    return _to_dict(tj)


def list_target_jobs(db: Session, *, user_id: int) -> dict:
    jobs = get_target_jobs(db, user_id)
    latest = get_latest_target_job(db, user_id)
    return {
        "items": [_to_dict(t) for t in jobs],
        "current": _to_dict(latest) if latest else None,
    }


def get_target_job_detail(db: Session, *, user_id: int, target_job_id: int) -> dict:
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    return _to_dict(tj)


def set_current_target_job(db: Session, *, user_id: int, target_job_id: int) -> dict:
    """Switch the workspace's "current" job to the given one.

    ``current`` is defined as the most recently updated job (see
    ``get_latest_target_job``), so switching = touching ``updated_at``. This
    keeps a single source of truth (no extra is_current flag to drift) and
    matches the product semantic: the workbench shows the job you are working
    on *now*.
    """
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    tj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tj)
    return _to_dict(tj)


# ----------------------------- F9 parse + confirm -----------------------------
def parse_jd(db: Session, *, user_id: int, target_job_id: int, raw_jd: str,
             job_title: str = "", company: str = "", city: str = "",
             direction_id: int | None = None) -> dict:
    """Run F9 on the raw JD; store the parse as a draft (jd_status=parsed).

    The AI output is validated + normalized by the program; the user still has
    to confirm before it becomes the official ability_model.
    """
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    if len(raw_jd.strip()) < 10:
        raise AppValidationError("JD 内容过短，请粘贴完整的岗位描述", code="jd_too_short")

    # Explore 带来的方向上下文：只在岗位尚未绑定方向时写入（不覆盖用户已有绑定），
    # 让「来自职业探索」的关联真实持久化，而不是只在 UI 上展示。
    if direction_id is not None and tj.direction_id is None:
        tj.direction_id = direction_id

    update_target_job(db, tj, source_jd={"raw_text": raw_jd, "parsed_json": {}}, jd_status="parsing")
    gateway = get_gateway()
    try:
        result = gateway.run(
            "f9_jd_parse",
            {"raw_jd": raw_jd, "job_title": job_title or tj.job_title,
             "company": company or tj.company, "city": city or tj.city},
        )
        parsed = result.data
        status = "ok" if result.status == "ok" else "fallback"
    except AIGatewayError:
        # Program-level fallback parse (keyword-light) -- JD creation still works.
        parsed = _fallback_parse(raw_jd, job_title or tj.job_title, company or tj.company)
        status = "fallback"

    normalized = _normalize_parse(parsed)
    tj.source_jd = {"raw_text": raw_jd, "parsed_json": normalized}
    # The parsed model is also stored as a *draft* ability_model so the user can
    # view + edit it before confirming. Confirm flips jd_status to "user_edited"
    # and is the only path that makes the model "official" / matchable.
    tj.ability_model = normalized
    if job_title:
        tj.job_title = job_title
    if company:
        tj.company = company
    if city:
        tj.city = city
    tj.jd_status = "parsed"
    db.commit()
    db.refresh(tj)
    return {"target_job": _to_dict(tj), "parse_status": status}


def confirm_target_job(db: Session, *, user_id: int, target_job_id: int,
                       ability_model: dict, industry: str = "", responsibilities: list | None = None,
                       other_requirements: list | None = None, job_title: str = "", company: str = "",
                       city: str = "") -> dict:
    """Persist the user-confirmed (and possibly edited) structured JD.

    The AI never overwrites this. After confirmation the job is matchable.
    """
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    if not ability_model or not ability_model.get("abilities"):
        raise AppValidationError("能力模型不能为空，请至少保留一项能力", code="empty_ability_model")

    am = _normalize_parse({"abilities": ability_model.get("abilities", []),
                           "requirements": ability_model.get("requirements", {}),
                           "responsibilities": responsibilities or tj.responsibilities,
                           "other_requirements": other_requirements or tj.other_requirements,
                           "industry": industry or tj.industry,
                           "title": job_title or tj.job_title,
                           "company": company or tj.company})
    tj.ability_model = am
    if industry:
        tj.industry = industry
    if responsibilities is not None:
        tj.responsibilities = responsibilities
    if other_requirements is not None:
        tj.other_requirements = other_requirements
    if job_title:
        tj.job_title = job_title
    if company:
        tj.company = company
    if city:
        tj.city = city
    tj.jd_status = "user_edited"
    db.commit()
    db.refresh(tj)
    return _to_dict(tj)


def delete_target_job_entry(db: Session, *, user_id: int, target_job_id: int) -> dict:
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    delete_target_job(db, tj)
    db.commit()
    return {"deleted": True}


# ----------------------------- helpers -----------------------------
def _normalize_parse(parsed: dict) -> dict:
    """Program-side normalization: enforce enums/bounds, drop junk."""
    abilities = []
    for ab in (parsed.get("abilities") or []):
        cat = (ab.get("category") or ab.get("requirement_type") or "hard").lower()
        if cat not in ("hard", "soft", "plus"):
            cat = "hard"
        try:
            level = int(ab.get("level", 3))
        except (TypeError, ValueError):
            level = 3
        level = max(1, min(5, level))
        try:
            weight = float(ab.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(0.0, min(2.0, weight))
        abilities.append({
            "name": (ab.get("name") or "").strip(),
            "category": cat,
            "requirement_type": cat,
            "level": level,
            "weight": weight,
        })
    abilities = [a for a in abilities if a["name"]]

    req = parsed.get("requirements") or {}
    try:
        exp_years = int(req.get("experience_years", 0) or 0)
    except (TypeError, ValueError):
        exp_years = 0
    requirements = {
        "education": str(req.get("education") or ""),
        "experience_years": max(0, exp_years),
        "major": list(req.get("major") or []),
        "cert": list(req.get("cert") or []),
    }
    return {
        "abilities": abilities,
        "requirements": requirements,
        "responsibilities": list(parsed.get("responsibilities") or []),
        "other_requirements": list(parsed.get("other_requirements") or []),
        "industry": str(parsed.get("industry") or ""),
        "title": str(parsed.get("title") or ""),
        "company": str(parsed.get("company") or ""),
    }


def _fallback_parse(raw_jd: str, job_title: str, company: str) -> dict:
    """Program-level fallback when the AI gateway is unavailable."""
    return {
        "company": company or "",
        "title": job_title or "",
        "industry": "",
        "responsibilities": [],
        "abilities": [
            {"name": "相关能力（待确认）", "category": "hard", "level": 3,
             "weight": 1.0, "requirement_type": "hard"}
        ],
        "requirements": {"education": "", "experience_years": 0, "major": [], "cert": []},
        "other_requirements": [],
    }


def _to_dict(tj) -> dict:
    return {
        "target_job_id": tj.id,
        "user_id": tj.user_id,
        "direction_id": tj.direction_id,
        "job_id": tj.job_id,
        "job_title": tj.job_title,
        "company": tj.company,
        "city": tj.city,
        "source_jd": tj.source_jd or {},
        "ability_model": tj.ability_model or {},
        "industry": tj.industry,
        "responsibilities": tj.responsibilities or [],
        "other_requirements": tj.other_requirements or [],
        "jd_status": tj.jd_status,
        "created_at": tj.created_at.isoformat() if tj.created_at else None,
        "updated_at": tj.updated_at.isoformat() if tj.updated_at else None,
    }
