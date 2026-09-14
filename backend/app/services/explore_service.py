"""Explore service (Phase 2).

Orchestrates the Explore workspace:
  * loads the user's career profile (unfolding the Phase 1B folded extras)
  * parses natural-language preference input into structured preferences
  * runs the deterministic recommender (program)
  * asks the AI (F4) to write the personal reason on top of each candidate
  * handles exclude / compare / candidate / target-job transitions
  * persists everything per-user so the page restores on refresh

Principles (per PRD + 方案):
  * AI only writes ``reason``; score/rank/exclusion/compare are program-owned.
  * Everything degrades gracefully when the AI is unavailable (fallback reason).
  * No scores/salary/verdicts are ever emitted by the AI.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError, get_gateway
from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.models.explore import Direction, ExploreState, Industry, Job
from app.repositories import get_profile
from app.repositories_explore import (
    get_all_directions,
    get_direction,
    get_explore_state,
    get_industries_by_ids,
    get_jobs_by_ids,
    get_or_create_explore_state,
    get_recommendation,
    get_recommendations,
    save_explore_state,
    set_recommendation_excluded,
    upsert_recommendation,
)
from app.services import recommender
from app.services.recommender import UserSignal


# ----------------------------- profile unfolding -----------------------------
def _unfold_profile(profile) -> dict:
    """Read career_profile, unfolding the Phase 1B folded extras from preference_infer."""
    if profile is None:
        return {}
    pref = dict(profile.preference_infer or {})
    ability_tags = [a.get("tag") for a in (profile.ability_tags or []) if a.get("tag")]
    interest_tags = [i.get("tag") for i in (profile.interest_tags or []) if i.get("tag")]
    strengths = [s.get("item") for s in (profile.strengths or []) if s.get("item")]
    return {
        "positioning": pref.get("positioning", ""),
        "tendencies": pref.get("tendencies", []),
        "motivations": pref.get("motivations", []),
        "gaps": pref.get("gaps", []),
        "career_goal": pref.get("career_goal", ""),
        "ability_tags": ability_tags,
        "interest_tags": interest_tags,
        "strengths": strengths,
        "risks": profile.risks or [],
    }


# ----------------------------- natural-language preference parsing -----------------------------
# The program parses the user's free-text exploration input into structured
# preferences. This keeps Explore usable with NO AI at all.
_AVOID_PATTERNS = [
    (r"不(想|要|做|考虑|喜欢).{0,6}(纯技术|写代码|敲代码|研发)", "纯技术"),
    (r"不(想|要|做).{0,6}(销售|地推)", "销售"),
    (r"不(想|要|做).{0,6}(加班|太累|熬夜)", "高强度加班"),
    (r"不(想|要).{0,6}(出差)", "频繁出差"),
]
_FIELD_MAP = {
    "互联网": "互联网", "软件": "互联网", "it": "互联网", "金融": "金融",
    "银行": "金融", "证券": "金融", "保险": "金融", "制造": "智能制造",
    "硬件": "智能制造", "嵌入式": "智能制造", "消费": "消费", "内容": "消费",
    "文创": "消费", "电商": "消费",
}
_VALUE_MAP = {
    "稳定": "value_stability", "安稳": "value_stability", "保障": "value_stability",
    "成长": "value_growth", "发展": "value_growth", "前景": "value_growth",
    "自主": "value_autonomy", "独立": "value_autonomy", "自由": "value_autonomy",
    "社交": "value_social", "沟通": "value_social", "人际": "value_social",
}
_CITY_PATTERN = r"(北京|上海|广州|深圳|杭州|成都|南京|武汉|西安|苏州)"


def parse_preference_text(text: str) -> dict:
    """Parse free text into a structured preference delta (program-only)."""
    text = (text or "").strip()
    out: dict = {"prefer_fields": [], "avoid_keywords": [], "value_flags": {}, "prefer_city": None}
    if not text:
        return out

    low = text.lower()
    # fields
    for kw, field in _FIELD_MAP.items():
        if kw.lower() in low and field not in out["prefer_fields"]:
            out["prefer_fields"].append(field)
    # values
    for kw, flag in _VALUE_MAP.items():
        if kw in text:
            out["value_flags"][flag] = True
    # avoid
    for pat, label in _AVOID_PATTERNS:
        if re.search(pat, text):
            if label not in out["avoid_keywords"]:
                out["avoid_keywords"].append(label)
    # city
    m = re.search(_CITY_PATTERN, text)
    if m:
        out["prefer_city"] = m.group(1)
    return out


# ----------------------------- core: compute recommendations -----------------------------
def _build_signal(db: Session, user_id: int) -> UserSignal:
    profile = get_profile(db, user_id)
    unfolded = _unfold_profile(profile)
    st = get_explore_state(db, user_id)
    prefs: dict = dict(st.preferences) if st else {}
    excluded = list(st.excluded_direction_ids) if st else []
    return UserSignal(
        ability_tags=unfolded.get("ability_tags", []),
        interest_tags=unfolded.get("interest_tags", []),
        strengths=unfolded.get("strengths", []),
        positioning=unfolded.get("positioning", ""),
        preferences=prefs,
        excluded_direction_ids=excluded,
    )


def compute_recommendations(db: Session, *, user_id: int, with_reason: bool = True) -> list[dict]:
    """Run the deterministic recommender and (optionally) ask F4 for reasons.

    Returns a list of recommendation dicts, highest score first, EXCLUDING
    directions the user excluded. Persists the scored rows.
    """
    directions = get_all_directions(db)
    sig = _build_signal(db, user_id)
    ranked = recommender.rank_directions(directions, sig)

    results: list[dict] = []
    for d, score, basis in ranked:
        if d.id in sig.excluded_direction_ids:
            # still persist as excluded so re-inclusion is possible
            upsert_recommendation(db, user_id=user_id, direction_id=d.id, score=score, match_basis=basis)
            continue
        rec = upsert_recommendation(db, user_id=user_id, direction_id=d.id, score=score, match_basis=basis)
        reason, reason_status = _ensure_reason(db, d, sig, rec, with_reason=with_reason)
        results.append(_rec_to_dict(d, rec, reason, reason_status, basis, score))

    db.commit()
    return results


def _ensure_reason(db: Session, d: Direction, sig: UserSignal, rec, *, with_reason: bool):
    """Get a reason: reuse if already generated, else call F4 (degrade on fail)."""
    if rec.reason and rec.reason_status == "ok":
        return rec.reason, rec.reason_status
    if not with_reason:
        return rec.reason, rec.reason_status
    gateway = get_gateway()
    try:
        result = gateway.run(
            "f4_direction_reason",
            {
                "direction_name": d.name,
                "direction_summary": d.summary,
                "direction_core_abilities": d.core_abilities,
                "direction_work_styles": d.work_styles,
                "user_positioning": sig.positioning,
                "user_ability_tags": sig.ability_tags,
                "user_interest_tags": sig.interest_tags,
                "user_strengths": sig.strengths,
                "match_basis": rec.match_basis,
            },
        )
        reason = result.data.get("reason", "")
        status = result.status  # "ok" or "fallback"
    except AIGatewayError:
        # Offline-safe reason: echo the program's deterministic match basis so
        # the card still has a human-readable explanation with no AI at all.
        basis = rec.match_basis or []
        reason = ("根据你的画像，" + "；".join(basis[:2]) + "。") if basis else \
            "这个方向与你的画像有一定契合度，建议进一步了解。"
        status = "fallback"
    rec.reason = reason
    rec.reason_status = status
    db.flush()
    return reason, status


def _rec_to_dict(d: Direction, rec, reason: str, reason_status: str, basis: list[str], score: float) -> dict:
    return {
        "direction_id": d.id,
        "name": d.name,
        "summary": d.summary,
        "description": d.description,
        "core_abilities": d.core_abilities,
        "work_styles": d.work_styles,
        "industry_ids": d.industry_ids,
        "job_ids": d.job_ids,
        "attributes": d.attributes,
        "not_good_for": d.not_good_for,
        "growth_path": d.growth_path,
        "score": score if rec is None else rec.score,
        "match_basis": basis if rec is None else rec.match_basis,
        "reason": reason,
        "reason_status": reason_status,
        "status": rec.status if rec else "active",
    }


# ----------------------------- public API surface -----------------------------
def get_explore_home(db: Session, *, user_id: int) -> dict:
    """Home state for the Explore page (restore-friendly)."""
    profile = get_profile(db, user_id)
    if profile is None or profile.status in (None, "generating"):
        return {"has_profile": False, "profile": None, "recommendations": [], "state": _empty_state()}

    st = get_or_create_explore_state(db, user_id)
    recs = get_recommendations(db, user_id)
    # If no recommendations computed yet, compute now.
    if not recs:
        compute_recommendations(db, user_id=user_id, with_reason=True)
        recs = get_recommendations(db, user_id)

    active = [r for r in recs if r.status == "active"]
    directions_by_id = {d.id: d for d in get_all_directions(db)}
    rec_list = []
    for r in active:
        d = directions_by_id.get(r.direction_id)
        if d is None:
            continue
        rec_list.append(_rec_to_dict(d, r, r.reason, r.reason_status, r.match_basis, r.score))

    return {
        "has_profile": True,
        "profile": _unfold_profile(profile),
        "recommendations": rec_list,
        "state": _state_to_dict(st),
    }


def _empty_state() -> dict:
    return {
        "preferences": {}, "excluded_direction_ids": [], "candidate_direction_ids": [],
        "compare_direction_ids": [], "target_direction_id": None,
    }


def _state_to_dict(st: ExploreState) -> dict:
    return {
        "preferences": st.preferences or {},
        "excluded_direction_ids": st.excluded_direction_ids or [],
        "candidate_direction_ids": st.candidate_direction_ids or [],
        "compare_direction_ids": st.compare_direction_ids or [],
        "target_direction_id": st.target_direction_id,
    }


def update_preference_text(db: Session, *, user_id: int, text: str) -> dict:
    """Parse natural-language input, merge into explore_state.preferences, recompute."""
    parsed = parse_preference_text(text)
    st = get_or_create_explore_state(db, user_id)
    prefs = dict(st.preferences or {})
    if parsed["prefer_fields"]:
        merged = list(prefs.get("prefer_fields") or [])
        for f in parsed["prefer_fields"]:
            if f not in merged:
                merged.append(f)
        prefs["prefer_fields"] = merged
    if parsed["avoid_keywords"]:
        merged = list(prefs.get("avoid_keywords") or [])
        for k in parsed["avoid_keywords"]:
            if k not in merged:
                merged.append(k)
        prefs["avoid_keywords"] = merged
    if parsed["prefer_city"]:
        prefs["prefer_city"] = parsed["prefer_city"]
    for flag, val in parsed["value_flags"].items():
        prefs[flag] = val
    st.preferences = prefs
    save_explore_state(db, st)
    # re-rank with new preferences
    recs = compute_recommendations(db, user_id=user_id, with_reason=True)
    return {"state": _state_to_dict(st), "recommendations": recs, "parsed": parsed}


def exclude_direction(db: Session, *, user_id: int, direction_id: int, excluded: bool) -> dict:
    st = get_or_create_explore_state(db, user_id)
    ids = list(st.excluded_direction_ids or [])
    if excluded and direction_id not in ids:
        ids.append(direction_id)
    elif not excluded and direction_id in ids:
        ids.remove(direction_id)
    st.excluded_direction_ids = ids
    set_recommendation_excluded(db, user_id=user_id, direction_id=direction_id, excluded=excluded)
    save_explore_state(db, st)
    recs = compute_recommendations(db, user_id=user_id, with_reason=True)
    return {"state": _state_to_dict(st), "recommendations": recs}


def toggle_candidate(db: Session, *, user_id: int, direction_id: int) -> dict:
    st = get_or_create_explore_state(db, user_id)
    ids = list(st.candidate_direction_ids or [])
    if direction_id in ids:
        ids.remove(direction_id)
    else:
        ids.append(direction_id)
    st.candidate_direction_ids = ids
    save_explore_state(db, st)
    return {"state": _state_to_dict(st)}


def set_compare(db: Session, *, user_id: int, direction_ids: list[int]) -> dict:
    if len(direction_ids) > 4:
        raise AppValidationError("最多同时对比 4 个方向", code="too_many_compare")
    for did in direction_ids:
        if get_direction(db, did) is None:
            raise NotFoundError(f"方向不存在: {did}")
    st = get_or_create_explore_state(db, user_id)
    st.compare_direction_ids = direction_ids
    save_explore_state(db, st)
    return {"state": _state_to_dict(st)}


def toggle_compare(db: Session, *, user_id: int, direction_id: int) -> dict:
    st = get_or_create_explore_state(db, user_id)
    ids = list(st.compare_direction_ids or [])
    if direction_id in ids:
        ids.remove(direction_id)
    elif len(ids) >= 4:
        raise AppValidationError("最多同时对比 4 个方向", code="too_many_compare")
    else:
        ids.append(direction_id)
    st.compare_direction_ids = ids
    save_explore_state(db, st)
    return {"state": _state_to_dict(st)}


def get_compare(db: Session, *, user_id: int) -> dict:
    st = get_or_create_explore_state(db, user_id)
    ids = st.compare_direction_ids or []
    directions = [d for d in (get_direction(db, i) for i in ids) if d is not None]
    sig = _build_signal(db, user_id)
    rows = recommender.build_compare_rows(directions, sig)
    advice = recommender.compare_advice(rows)
    return {"rows": rows, "advice": advice}


def get_direction_detail(db: Session, *, direction_id: int) -> dict:
    d = get_direction(db, direction_id)
    if d is None:
        raise NotFoundError("方向不存在")
    industries = get_industries_by_ids(db, d.industry_ids)
    jobs = get_jobs_by_ids(db, d.job_ids)
    return {
        "direction": _rec_to_dict(d, None, "", "pending", [], 0.0),
        "industries": [{"id": i.id, "name": i.name, "description": i.description, "traits": i.traits} for i in industries],
        "jobs": [
            {"id": j.id, "name": j.name, "description": j.description,
             "required_abilities": j.required_abilities, "entry_barrier": j.entry_barrier,
             "work_styles": j.work_styles}
            for j in jobs
        ],
    }


def get_industry_detail(db: Session, *, industry_id: int) -> dict:
    from sqlalchemy import select

    ind = db.get(Industry, industry_id)
    if ind is None:
        raise NotFoundError("行业不存在")
    jobs = list(db.scalars(select(Job).where(Job.industry_id == industry_id)).all())
    return {
        "id": ind.id, "name": ind.name, "description": ind.description,
        "traits": ind.traits, "work_styles": ind.work_styles,
        "jobs": [{"id": j.id, "name": j.name, "description": j.description,
                  "required_abilities": j.required_abilities, "entry_barrier": j.entry_barrier}
                 for j in jobs],
    }


def get_job_detail(db: Session, *, job_id: int) -> dict:
    j = db.get(Job, job_id)
    if j is None:
        raise NotFoundError("岗位不存在")
    return {
        "id": j.id, "name": j.name, "description": j.description,
        "required_abilities": j.required_abilities, "entry_barrier": j.entry_barrier,
        "work_styles": j.work_styles,
    }


def set_target_direction(db: Session, *, user_id: int, direction_id: int) -> dict:
    d = get_direction(db, direction_id)
    if d is None:
        raise NotFoundError("方向不存在")
    st = get_or_create_explore_state(db, user_id)
    st.target_direction_id = direction_id
    # reflect into candidate set too
    ids = list(st.candidate_direction_ids or [])
    if direction_id not in ids:
        ids.append(direction_id)
        st.candidate_direction_ids = ids
    save_explore_state(db, st)
    return {"state": _state_to_dict(st), "target_direction_id": direction_id}
