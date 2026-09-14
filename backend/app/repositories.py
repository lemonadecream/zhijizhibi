"""Repository layer: all direct DB access lives here.

Services call these functions; they never touch ORM models directly. This keeps
the persistence details isolated and makes the data access testable.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.experience import (
    CareerGoal,
    EducationExp,
    Interest,
    InternshipExp,
    ProjectExp,
    Skill,
    WorkPreference,
)
from app.models.resume import CareerProfile, ProfileRevisionLog, Resume
from app.models.user import User, UserProfile


# ----------------------------- User -----------------------------
def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_phone(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, *, email: str | None, phone: str | None, password_hash: str) -> User:
    user = User(email=email, phone=phone, password_hash=password_hash)
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


# ----------------------------- Resume -----------------------------
def create_resume(db: Session, *, user_id: int, file_id: str | None, filename: str | None) -> Resume:
    r = Resume(user_id=user_id, file_id=file_id, filename=filename, parse_status="pending")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def set_resume_text(db: Session, resume_id: int, raw_text: str) -> Resume:
    r = db.get(Resume, resume_id)
    r.raw_text = raw_text
    r.parse_status = "parsing"
    db.commit()
    db.refresh(r)
    return r


def save_resume_parse_result(db: Session, resume_id: int, parsed_json: dict, *, failed: bool = False, error: str | None = None) -> Resume:
    r = db.get(Resume, resume_id)
    r.parsed_json = parsed_json
    r.parse_status = "failed" if failed else "parsed"
    r.error = error
    db.commit()
    db.refresh(r)
    return r


def get_resume(db: Session, resume_id: int, user_id: int) -> Resume | None:
    r = db.get(Resume, resume_id)
    if r is None or r.user_id != user_id:
        return None
    return r


# ----------------------------- Experiences -----------------------------
def _clear_experiences(db: Session, user_id: int) -> None:
    for cls in (EducationExp, InternshipExp, ProjectExp, Skill, Interest):
        db.query(cls).filter(cls.user_id == user_id).delete()


def _remap_exp(e: dict) -> dict:
    """Rename API/F1 keys to model column names so dates/descriptions aren't lost.

    F1 / manual input uses ``start``/``end``/``duty``/``desc``; the experience
    models persist ``start_date``/``end_date``/``duty_desc``/``description``.
    """
    rename = {
        "start": "start_date",
        "end": "end_date",
        "duty": "duty_desc",
        "desc": "description",
    }
    return {rename.get(k, k): v for k, v in e.items()}


def save_experiences_from_parsed(db: Session, user_id: int, parsed: dict) -> None:
    """Persist confirmed F1 draft into experience tables (overwrites previous)."""
    _clear_experiences(db, user_id)

    for e in parsed.get("education", []):
        db.add(EducationExp(user_id=user_id, source="ai", **_pick(_remap_exp(e), EducationExp)))
    for e in parsed.get("internships", []):
        db.add(InternshipExp(user_id=user_id, source="ai", **_pick(_remap_exp(e), InternshipExp)))
    for e in parsed.get("projects", []):
        db.add(ProjectExp(user_id=user_id, source="ai", **_pick(_remap_exp(e), ProjectExp)))
    for s in parsed.get("skills", []):
        db.add(Skill(user_id=user_id, source="ai", name=s["name"], level=s.get("level")))
    for tag in parsed.get("interests", []):
        db.add(Interest(user_id=user_id, source="ai", tag=tag))

    db.commit()


def save_manual_experiences(db: Session, user_id: int, parsed: dict) -> None:
    """Persist manually entered experiences (source=user)."""
    _clear_experiences(db, user_id)
    for e in parsed.get("education", []):
        db.add(EducationExp(user_id=user_id, source="user", **_pick(_remap_exp(e), EducationExp)))
    for e in parsed.get("internships", []):
        db.add(InternshipExp(user_id=user_id, source="user", **_pick(_remap_exp(e), InternshipExp)))
    for e in parsed.get("projects", []):
        db.add(ProjectExp(user_id=user_id, source="user", **_pick(_remap_exp(e), ProjectExp)))
    for s in parsed.get("skills", []):
        db.add(Skill(user_id=user_id, source="user", name=s["name"], level=s.get("level")))
    for tag in parsed.get("interests", []):
        db.add(Interest(user_id=user_id, source="user", tag=tag))
    db.commit()


def _pick(d: dict, cls) -> dict:
    cols = {c.name for c in cls.__table__.columns}
    cols -= {"id", "user_id", "source", "created_at", "updated_at"}
    return {k: v for k, v in d.items() if k in cols}


def get_experiences(db: Session, user_id: int) -> dict:
    """Assemble confirmed experiences into a compact dict for F2 context."""
    out: list[dict] = []
    for e in db.scalars(select(EducationExp).where(EducationExp.user_id == user_id)).all():
        out.append({"type": "education", "title": f"{e.school} {e.major}", "detail": f"{e.degree or ''} {e.start_date or ''}~{e.end_date or ''}"})
    for e in db.scalars(select(InternshipExp).where(InternshipExp.user_id == user_id)).all():
        out.append({"type": "internship", "title": f"{e.company} {e.role}", "detail": e.duty_desc or ""})
    for e in db.scalars(select(ProjectExp).where(ProjectExp.user_id == user_id)).all():
        out.append({"type": "project", "title": e.name, "detail": e.description or ""})
    for s in db.scalars(select(Skill).where(Skill.user_id == user_id)).all():
        out.append({"type": "skill", "title": s.name, "detail": f"level {s.level or '-'}"})
    return out


def get_preference(db: Session, user_id: int) -> dict | None:
    wp = db.get(WorkPreference, user_id)
    if not wp:
        return None
    return {
        "city": wp.city,
        "company_types": wp.company_types,
        "industries": wp.industries,
        "salary_expect": wp.salary_expect,
        "overtime_tolerance": wp.overtime_tolerance,
        "stability_pref": wp.stability_pref,
    }


# ----------------------------- Career profile -----------------------------
def get_profile(db: Session, user_id: int) -> CareerProfile | None:
    return db.scalar(select(CareerProfile).where(CareerProfile.user_id == user_id).order_by(CareerProfile.version.desc()))


def create_profile(db: Session, user_id: int, data: dict, *, status: str = "generating") -> CareerProfile:
    p = CareerProfile(user_id=user_id, status=status, **_profile_cols(data))
    db.add(p)
    db.flush()
    db.add(ProfileRevisionLog(user_id=user_id, version=p.version, change_type="create", changed_fields=list(data.keys())))
    db.commit()
    db.refresh(p)
    return p


def update_profile(db: Session, user_id: int, data: dict) -> CareerProfile:
    existing = get_profile(db, user_id)
    if existing is None:
        return create_profile(db, user_id, data, status="edited")
    new_version = existing.version + 1
    p = CareerProfile(user_id=user_id, version=new_version, status="edited", **_profile_cols(data))
    db.add(p)
    db.flush()
    db.add(ProfileRevisionLog(user_id=user_id, version=new_version, change_type="edit", changed_fields=list(data.keys())))
    db.commit()
    db.refresh(p)
    return p


# Phase 1B extras that don't have dedicated columns are folded into the
# free-form ``preference_infer`` JSON column so they persist without a schema
# migration, while remaining backward-compatible with older profiles.
_EXTRA_KEYS = ("positioning", "tendencies", "motivations", "gaps", "career_goal")


def _fold_extras(data: dict) -> dict:
    pref = dict(data.get("preference_infer") or {})
    for k in _EXTRA_KEYS:
        if k in data and data[k] not in (None, [], {}):
            pref[k] = data[k]
        elif k in pref:
            # keep stored extra unless explicitly cleared
            pass
    return pref


def set_profile_status(db: Session, profile_id: int, status: str) -> None:
    p = db.get(CareerProfile, profile_id)
    if p:
        p.status = status
        db.commit()


def create_profile_placeholder(db: Session, user_id: int) -> CareerProfile:
    p = CareerProfile(
        user_id=user_id,
        status="generating",
        ability_tags=[],
        interest_tags=[],
        strengths=[],
        risks=[],
        preference_infer={},
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def fill_profile(db: Session, profile_id: int, data: dict, *, ai_failed: bool = False) -> CareerProfile:
    p = db.get(CareerProfile, profile_id)
    p.ability_tags = data.get("ability_tags", [])
    p.interest_tags = data.get("interest_tags", [])
    p.strengths = data.get("strengths", [])
    p.risks = data.get("risks", [])
    p.preference_infer = _fold_extras(data)
    if ai_failed:
        p.preference_infer = {**p.preference_infer, "_ai_failed": True}
    p.status = "ready"
    db.commit()
    db.refresh(p)
    return p


def _profile_cols(data: dict) -> dict:
    return {
        "ability_tags": data.get("ability_tags", []),
        "interest_tags": data.get("interest_tags", []),
        "strengths": data.get("strengths", []),
        "risks": data.get("risks", []),
        "preference_infer": _fold_extras(data),
    }
