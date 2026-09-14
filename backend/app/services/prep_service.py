"""Preparation service (Phase 4): F12 + F14 + F13.

Full flow:
  target_job (confirmed) + match_result + capability_gap (Phase 3, single source
  of truth) + career_profile + experiences
    -> F12 preparation plan (AI writes why/how per gap; program owns priority,
       status, progress, sorting, staleness)
    -> F14 interview focus (AI predicts questions grounded in real experiences)
    -> F13 resume advice (AI gives lightweight, targeted resume tweaks)

Principles (per PRD V0.2 + Phase 4 纪律):
  * Phase 4 NEVER re-parses the JD, re-runs the match, or re-judges a gap.
    ``capability_gap`` is consumed as-is.
  * The score / priority / completion / staleness are PROGRAM-owned. AI only
    writes natural-language suggestions and explanations.
  * If the AI fails, keep the program-determinable result and use the gateway
    fallback so the whole workspace works offline.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError, get_gateway
from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.repositories import get_experiences, get_profile
from app.repositories_prepare import (
    delete_tasks_by_ability,
    get_interview_focus,
    get_prep_plan,
    get_prep_plan_by_id,
    get_resume_advice,
    get_task,
    get_tasks_by_plan,
    replace_interview_focus,
    replace_resume_advice,
    upsert_prep_plan,
    add_task,
    update_task,
    get_target_job_for_user,
    get_latest_target_job,
)
from app.repositories_target_job import get_gaps_by_match, get_match_result
from app.services.explore_service import _unfold_profile  # reuse profile unfolding


# ----------------------------- context loader -----------------------------
def _load_context(db: Session, *, user_id: int, target_job_id: int) -> dict:
    """Resolve the (target_job, match, gaps, profile, experiences) tuple.

    Raises if the target job isn't owned by the user, or if there's no match yet
    (Preparation depends on Phase 3's match + gaps).
    """
    tj = get_target_job_for_user(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在或不属于当前用户")
    match = get_match_result(db, user_id, target_job_id)
    if match is None:
        raise AppValidationError("请先在目标岗位完成匹配（生成 Gap）后再准备", code="no_match")
    gaps = get_gaps_by_match(db, user_id, match.id)
    profile = get_profile(db, user_id)
    unfolded = _unfold_profile(profile) if profile else {}
    experiences = get_experiences(db, user_id)
    return {
        "target_job": tj,
        "match": match,
        "gaps": gaps,
        "profile": unfolded,
        "experiences": experiences,
    }


def _gap_to_ai(gap) -> dict:
    """Serialize a CapabilityGap for AI prompts (no AI-authored fields leaked)."""
    return {
        "ability": gap.ability,
        "priority": gap.priority,
        "why": gap.why,
        "evidence": gap.evidence,
        "improvement_direction": gap.improvement_direction,
        "gap_degree": gap.gap_degree,
    }


def _match_signature(match, gaps) -> str:
    """Stable signature of the match + gaps an artifact was built against.

    ``match_result`` is upserted (same ``match.id`` reused across re-matches), so
    comparing ids alone can never tell that the match was recomputed or the JD
    reparsed. This captures the parts that actually drive preparation output:
    the program score, the per-ability relation verdicts, and the gap set.
    """
    rel = match.relation_judgements or []
    rel_key = sorted(
        [(r.get("ability"), r.get("relation")) for r in rel if isinstance(r, dict)]
    )
    gap_key = sorted([(g.ability, round(float(g.gap_degree), 2)) for g in gaps])
    payload = {
        "score": round(float(match.total_score), 1),
        "rel": rel_key,
        "gaps": gap_key,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ----------------------------- home (aggregate) -----------------------------
def get_prep_home(db: Session, *, user_id: int, target_job_id: int | None = None) -> dict:
    """Single payload the /prepare page needs.

    Returns has_target / has_match / stale flags / prep_plan(+tasks) / interview /
    resume. The frontend restores everything from this on refresh (no extra call).
    """
    tj = (
        get_target_job_for_user(db, user_id, target_job_id)
        if target_job_id
        else get_latest_target_job(db, user_id)
    )
    if tj is None:
        return {"has_target": False, "has_match": False, "target_job": None,
                "match_summary": None, "gaps": [], "prep_plan": None, "tasks": [],
                "interview_focus": [], "resume_advice": [],
                "prep_stale": False, "interview_stale": False, "resume_stale": False}

    match = get_match_result(db, user_id, tj.id)
    if match is None:
        return {"has_target": True, "has_match": False, "target_job": _tj_to_dict(tj),
                "match_summary": None, "gaps": [], "prep_plan": None, "tasks": [],
                "interview_focus": [], "resume_advice": [],
                "prep_stale": False, "interview_stale": False, "resume_stale": False}

    gaps = get_gaps_by_match(db, user_id, match.id)
    plan = get_prep_plan(db, user_id, tj.id)
    tasks = get_tasks_by_plan(db, user_id, plan.id) if plan else []
    interview = get_interview_focus(db, user_id, tj.id)
    resume = get_resume_advice(db, user_id, tj.id)

    # Staleness: match.id is upserted/stable, so compare the stored match
    # signature against the current match + gaps signature instead.
    sig = _match_signature(match, gaps)
    prep_stale = bool(plan) and plan.match_snapshot != sig
    interview_stale = bool(interview) and interview[0].match_snapshot != sig
    resume_stale = bool(resume) and resume[0].match_snapshot != sig

    return {
        "has_target": True,
        "has_match": True,
        "target_job": _tj_to_dict(tj),
        "match_summary": {
            "total_score": match.total_score,
            "ai_status": match.ai_status,
            "gap_count": len(gaps),
        },
        "gaps": [_gap_to_dict(g) for g in gaps],
        "prep_plan": _plan_to_dict(plan) if plan else None,
        "tasks": [_task_to_dict(t) for t in tasks],
        "interview_focus": [_focus_to_dict(f) for f in interview],
        "resume_advice": [_advice_to_dict(a) for a in resume],
        "prep_stale": prep_stale,
        "interview_stale": interview_stale,
        "resume_stale": resume_stale,
    }


# ----------------------------- F12: preparation plan -----------------------------
def generate_prep_plan(db: Session, *, user_id: int, target_job_id: int) -> dict:
    """Consume Phase 3 gaps -> AI prep advice -> persist tasks (preserving edits)."""
    ctx = _load_context(db, user_id=user_id, target_job_id=target_job_id)
    tj = ctx["target_job"]
    match = ctx["match"]
    gaps = ctx["gaps"]

    # Stale-detection signature of the match + gaps this plan is built against.
    sig = _match_signature(match, gaps)

    # --- F12: AI writes why/how per gap; program owns priority/status/progress.
    gateway = get_gateway()
    ai_items: list[dict] = []
    ai_status = "ok"
    try:
        result = gateway.run(
            "f12_preparation_plan",
            {
                "job_title": tj.job_title,
                "company": tj.company,
                "gaps": [_gap_to_ai(g) for g in gaps],
            },
        )
        ai_items = result.data.get("prep_items", [])
        ai_status = "ok" if result.status == "ok" else "fallback"
    except AIGatewayError:
        ai_status = "fallback"

    # Build an ability -> AI item map (fallback already keyed by ability).
    ai_map = {it.get("ability"): it for it in ai_items if isinstance(it, dict)}

    plan = upsert_prep_plan(
        db, user_id=user_id, target_job_id=target_job_id, match_id=match.id,
        match_snapshot=sig, status="ready",
    )
    # P0-1: persist which AI path actually produced the advice so the Prepare
    # plan can show an honest status badge on reload (not just at generate time).
    plan.ai_status = ai_status
    existing = {t.ability: t for t in get_tasks_by_plan(db, user_id, plan.id)}

    gap_abilities: set[str] = set()
    order = 0
    for gap in gaps:
        ability = gap.ability
        gap_abilities.add(ability)
        ai = ai_map.get(ability, {})
        priority = gap.priority  # program-owned default
        if ability in existing:
            task = existing[ability]
            # Protect user-authored fields if the user has edited this task.
            if not task.is_user_edited:
                task.title = ai.get("title", task.title) or f"补齐「{ability}」能力"
                task.reason = ai.get("reason", task.reason)
                task.action_suggestion = ai.get("action_suggestion", task.action_suggestion)
                if not task.user_priority_override:
                    task.priority = priority
            task.gap_id = gap.id
            task.current_situation = gap.why
            task.order = order
        else:
            task = add_task(
                db, user_id=user_id, plan_id=plan.id,
                gap_id=gap.id, ability=ability,
                title=ai.get("title", "") or f"补齐「{ability}」能力",
                reason=ai.get("reason", ""),
                current_situation=gap.why,
                action_suggestion=ai.get("action_suggestion", ""),
                priority=priority,
                status="pending",
                user_note="",
                is_user_edited=False,
                order=order,
            )
        order += 1

    # Drop tasks whose gap no longer exists (gap closed by a fresh match).
    delete_tasks_by_ability(db, user_id=user_id, plan_id=plan.id, abilities=gap_abilities)

    db.commit()
    db.refresh(plan)
    _recompute_plan(db, plan)
    db.commit()

    tasks = get_tasks_by_plan(db, user_id, plan.id)
    return {"prep_plan": _plan_to_dict(plan), "tasks": [_task_to_dict(t) for t in tasks],
            "ai_status": ai_status}


def update_prep_task(db: Session, *, user_id: int, task_id: int, **fields) -> dict:
    """Update one preparation task (status / priority / note / human fields).

    Editing a human field (title/reason/action/user_note) sets ``is_user_edited``
    so a later regenerate won't overwrite it. Changing priority sets
    ``user_priority_override``. Recomputes plan progress + status.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        raise NotFoundError("准备任务不存在或不属于当前用户")

    human_fields = {"title", "reason", "action_suggestion", "user_note"}
    edited_human = False
    for k in human_fields:
        if k in fields:
            setattr(task, k, fields[k])
            edited_human = True
    if "status" in fields and fields["status"] in ("pending", "done"):
        task.status = fields["status"]
    if "priority" in fields and fields["priority"] in ("high", "medium", "low"):
        task.priority = fields["priority"]
        task.user_priority_override = True
    if edited_human:
        task.is_user_edited = True

    db.commit()
    plan = get_prep_plan_by_id(db, user_id, task.plan_id) if task.plan_id else None
    if plan is not None:
        _recompute_plan(db, plan)
        db.commit()
    return {"task": _task_to_dict(task)}


def _recompute_plan(db: Session, plan) -> None:
    """Program-owned: derive overall_progress + status from task completion."""
    tasks = get_tasks_by_plan(db, plan.user_id, plan.id)
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == "done")
    plan.overall_progress = round((done / total) * 100, 1) if total else 100.0
    plan.status = "completed" if (total > 0 and done == total) else "ready"


# ----------------------------- F14: interview focus -----------------------------
def generate_interview_focus(db: Session, *, user_id: int, target_job_id: int) -> dict:
    ctx = _load_context(db, user_id=user_id, target_job_id=target_job_id)
    tj = ctx["target_job"]
    match = ctx["match"]
    gaps = ctx["gaps"]
    gateway = get_gateway()
    ai_status = "ok"
    try:
        result = gateway.run(
            "f14_interview_focus",
            {
                "job_title": tj.job_title,
                "company": tj.company,
                "abilities": tj.ability_model.get("abilities", []),
                "responsibilities": tj.responsibilities or [],
                "gaps": [_gap_to_ai(g) for g in ctx["gaps"]],
                "profile_positioning": ctx["profile"].get("positioning", ""),
                "ability_tags": ctx["profile"].get("ability_tags", []),
                "strengths": ctx["profile"].get("strengths", []),
                "experiences": ctx["experiences"],
            },
        )
        items = result.data.get("focus_items", [])
        ai_status = "ok" if result.status == "ok" else "fallback"
    except AIGatewayError:
        items = []
        ai_status = "fallback"

    rows = replace_interview_focus(
        db, user_id=user_id, target_job_id=target_job_id, match_id=match.id,
        match_snapshot=_match_signature(match, gaps),
        items=[{
            "question": it.get("question", ""),
            "reason": it.get("reason", ""),
            "related_requirement": it.get("related_requirement", ""),
            "related_experience": it.get("related_experience", ""),
            "preparation_advice": it.get("preparation_advice", ""),
            "evidence_status": it.get("evidence_status", "none"),
            "ai_status": ai_status,
        } for it in items],
    )
    db.commit()
    return {"interview_focus": [_focus_to_dict(r) for r in rows], "ai_status": ai_status}


def get_interview_focus_list(db: Session, *, user_id: int, target_job_id: int) -> dict:
    rows = get_interview_focus(db, user_id, target_job_id)
    return {"interview_focus": [_focus_to_dict(r) for r in rows]}


# ----------------------------- F13: resume advice -----------------------------
def generate_resume_advice(db: Session, *, user_id: int, target_job_id: int) -> dict:
    ctx = _load_context(db, user_id=user_id, target_job_id=target_job_id)
    tj = ctx["target_job"]
    match = ctx["match"]
    gaps = ctx["gaps"]
    gateway = get_gateway()
    ai_status = "ok"
    try:
        result = gateway.run(
            "f13_resume_advice",
            {
                "job_title": tj.job_title,
                "company": tj.company,
                "strengths": match.strengths or [],
                "risks": match.risks or [],
                "gaps": [_gap_to_ai(g) for g in ctx["gaps"]],
                "ability_tags": ctx["profile"].get("ability_tags", []),
                "experiences": ctx["experiences"],
            },
        )
        items = result.data.get("advices", [])
        ai_status = "ok" if result.status == "ok" else "fallback"
    except AIGatewayError:
        items = []
        ai_status = "fallback"

    rows = replace_resume_advice(
        db, user_id=user_id, target_job_id=target_job_id, match_id=match.id,
        match_snapshot=_match_signature(match, gaps),
        items=[{
            "advice_type": it.get("advice_type", ""),
            "content": it.get("content", ""),
            "related_experience": it.get("related_experience", ""),
            "related_gap": it.get("related_gap", ""),
            "severity": it.get("severity", "medium"),
            "ai_status": ai_status,
        } for it in items],
    )
    db.commit()
    return {"resume_advice": [_advice_to_dict(r) for r in rows], "ai_status": ai_status}


def get_resume_advice_list(db: Session, *, user_id: int, target_job_id: int) -> dict:
    rows = get_resume_advice(db, user_id, target_job_id)
    return {"resume_advice": [_advice_to_dict(r) for r in rows]}


# ----------------------------- dict helpers -----------------------------
def _tj_to_dict(tj) -> dict:
    return {
        "target_job_id": tj.id,
        "job_title": tj.job_title,
        "company": tj.company,
        "city": tj.city,
        "industry": tj.industry,
        "jd_status": tj.jd_status,
    }


def _gap_to_dict(gap) -> dict:
    return {
        "gap_id": gap.id,
        "ability": gap.ability,
        "priority": gap.priority,
        "gap_degree": gap.gap_degree,
        "why": gap.why,
        "evidence": gap.evidence,
        "improvement_direction": gap.improvement_direction,
        "status": gap.status,
    }


def _plan_to_dict(plan) -> dict:
    if plan is None:
        return None
    return {
        "plan_id": plan.id,
        "target_job_id": plan.target_job_id,
        "match_id": plan.match_id,
        "status": plan.status,
        "overall_progress": plan.overall_progress,
        "ai_status": plan.ai_status,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _task_to_dict(task) -> dict:
    return {
        "task_id": task.id,
        "plan_id": task.plan_id,
        "gap_id": task.gap_id,
        "ability": task.ability,
        "title": task.title,
        "reason": task.reason,
        "current_situation": task.current_situation,
        "action_suggestion": task.action_suggestion,
        "priority": task.priority,
        "user_priority_override": task.user_priority_override,
        "status": task.status,
        "user_note": task.user_note,
        "is_user_edited": task.is_user_edited,
        "order": task.order,
    }


def _focus_to_dict(f) -> dict:
    return {
        "focus_id": f.id,
        "question": f.question,
        "reason": f.reason,
        "related_requirement": f.related_requirement,
        "related_experience": f.related_experience,
        "preparation_advice": f.preparation_advice,
        "evidence_status": f.evidence_status,
        "ai_status": f.ai_status,
    }


def _advice_to_dict(a) -> dict:
    return {
        "advice_id": a.id,
        "advice_type": a.advice_type,
        "content": a.content,
        "related_experience": a.related_experience,
        "related_gap": a.related_gap,
        "severity": a.severity,
        "ai_status": a.ai_status,
    }
