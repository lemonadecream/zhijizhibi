"""Match service (Phase 3 Target Job): F10 + F11.

Full flow:
  target_job confirmed
    -> load career_profile (unfolded) + experiences
    -> F10 semantic judge (AI only emits covered/partial/missing + reason)
    -> PROGRAM computes total_score / dimensions / strengths / risks
    -> F11 gap explanation (AI only explains; program owns degree + priority)
    -> capability_gap rows persisted

Principles (per PRD + 方案 + 实施前审查报告):
  * The score is ALWAYS program-computed. AI never writes a number.
  * Covered = 1.0, Partial = 0.5, Missing = 0.0 coverage.
  * Default relation thresholds: covered >= 0.7, partial >= 0.4, missing < 0.4.
  * If the AI fails, keep the program-determinable result and mark the match
    ai_status="fallback"; gaps without an explanation show "AI解释暂不可用".
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError, get_gateway
from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.repositories import get_experiences, get_profile
from app.repositories_target_job import (
    get_gap,
    get_gaps_by_match,
    get_match_result,
    get_target_job,
    replace_gaps,
    save_match_result,
)
from app.services.explore_service import _unfold_profile  # reuse profile unfolding


# Relation -> coverage value (program-owned).
_COVERAGE = {"covered": 1.0, "partial": 0.5, "missing": 0.0}

# Gap degree thresholds (program-owned): <0.3 high gap, 0.3-0.6 medium, >=0.6 low.
_GAP_HIGH = 0.3
_GAP_LOW = 0.6


def run_match(db: Session, *, user_id: int, target_job_id: int) -> dict:
    """Execute F10 + program scoring + F11 + persist. Returns the match result."""
    tj = get_target_job(db, user_id, target_job_id)
    if tj is None:
        raise NotFoundError("目标岗位不存在")
    if tj.jd_status != "user_edited":
        raise AppValidationError("请先解析并确认 JD 能力模型后再匹配", code="jd_not_ready")

    profile = get_profile(db, user_id)
    if profile is None:
        raise AppValidationError("还没有职业画像，请先完成职业画像", code="no_profile")
    unfolded = _unfold_profile(profile)
    experiences = get_experiences(db, user_id)

    ability_model = tj.ability_model
    # --- F10: AI judges relation per ability (never a score) ---
    gateway = get_gateway()
    try:
        result = gateway.run(
            "f10_match_judge",
            {
                "profile_ability_tags": unfolded.get("ability_tags", []),
                "profile_strengths": unfolded.get("strengths", []),
                "experiences": experiences,
                "ability_model": ability_model,
            },
        )
        judgements = result.data.get("judgements", [])
        ai_status = "ok" if result.status == "ok" else "fallback"
    except AIGatewayError:
        judgements = []
        ai_status = "fallback"

    # Build a relation map; fill any missing ability with a program keyword match.
    relation_map = {j["ability"]: j for j in judgements if isinstance(j, dict)}
    enriched = []
    for ab in ability_model.get("abilities", []):
        name = ab.get("name", "")
        j = relation_map.get(name)
        if j is None:
            j = _keyword_relation(name, unfolded, experiences)
        relation = j.get("relation", "missing")
        enriched.append({
            "ability": name,
            "category": ab.get("category", "hard"),
            "requirement_type": ab.get("requirement_type", ab.get("category", "hard")),
            "level": ab.get("level", 3),
            "weight": ab.get("weight", 1.0),
            "relation": relation,
            "coverage": _COVERAGE.get(relation, 0.0),
            "reason": j.get("reason", ""),
            "evidence": j.get("evidence", ""),
        })

    # --- PROGRAM computes the match result ---
    total_score, dimension_scores, strengths, risks = _compute_score(enriched)

    match = save_match_result(
        db, user_id=user_id, target_job_id=target_job_id,
        profile_version=profile.version,
        jd_version=1,
        total_score=total_score,
        dimension_scores=dimension_scores,
        strengths=strengths,
        risks=risks,
        relation_judgements=enriched,
        ai_status=ai_status,
    )
    db.commit()
    db.refresh(match)

    # --- F11: explain gaps (AI only explains; program owns degree/priority) ---
    gaps = _build_gaps(db, user_id=user_id, match_id=match.id, enriched=enriched,
                       unfolded=unfolded, experiences=experiences, ai_status=ai_status)
    # Persist gaps: get_db does not auto-commit, so without this the gap rows
    # live only in the request session and are lost on close (Phase 3 tests
    # passed by inspecting the in-memory response; cross-request consumers such
    # as Phase 4 preparation depend on the rows being durable).
    db.commit()

    return {
        "match": _match_to_dict(match),
        "gaps": [_gap_to_dict(g) for g in gaps],
    }


def get_match(db: Session, *, user_id: int, target_job_id: int) -> dict | None:
    match = get_match_result(db, user_id, target_job_id)
    if match is None:
        return None
    gaps = get_gaps_by_match(db, user_id, match.id)
    return {"match": _match_to_dict(match), "gaps": [_gap_to_dict(g) for g in gaps]}


# ----------------------------- program scoring -----------------------------
def _compute_score(enriched: list[dict]) -> tuple[float, list, list, list]:
    """Program-owned scoring. Weighted coverage -> 0..100 total.

    Dimensions: 硬技能 (hard), 软技能 (soft), 加分项 (plus weight counted at 0.5).
    Strengths = covered abilities; Risks = missing / low-coverage hard abilities.
    """
    if not enriched:
        return 0.0, [], [], []

    total_w = 0.0
    acc = 0.0
    dim_acc = {"hard": [0.0, 0.0], "soft": [0.0, 0.0], "plus": [0.0, 0.0]}
    strengths: list[dict] = []
    risks: list[dict] = []

    for e in enriched:
        w = float(e.get("weight", 1.0))
        cov = float(e.get("coverage", 0.0))
        cat = e.get("category", "hard")
        # plus items count at half weight toward the headline score.
        eff_w = w if cat != "plus" else w * 0.5
        total_w += eff_w
        acc += eff_w * cov
        d = dim_acc.get(cat, dim_acc["hard"])
        d[0] += eff_w
        d[1] += eff_w * cov

        if e["relation"] == "covered":
            strengths.append({
                "ability": e["ability"], "category": cat,
                "evidence": e.get("evidence", ""),
            })
        elif e["relation"] == "missing" or (e["relation"] == "partial" and cat == "hard"):
            risks.append({
                "ability": e["ability"], "relation": e["relation"],
                "category": cat, "evidence": e.get("evidence", ""),
                "reason": e.get("reason", ""),
            })

    total = round((acc / total_w) * 100, 1) if total_w else 0.0
    dimensions = []
    for axis, (w, a) in dim_acc.items():
        score = round((a / w) * 100, 1) if w else 0.0
        label = {"hard": "硬技能要求", "soft": "软性素质", "plus": "加分项"}[axis]
        dimensions.append({"axis": label, "category": axis, "score": score})
    return total, dimensions, strengths, risks


# ----------------------------- F11 gaps -----------------------------
def _build_gaps(db: Session, *, user_id: int, match_id: int, enriched: list[dict],
                unfolded: dict, experiences: list, ai_status: str) -> list:
    """Program identifies gaps (partial/missing) + computes degree/priority,
    then asks AI (f11) for the explanation; degrades gracefully."""
    gateway = get_gateway()
    gap_rows = []
    for e in enriched:
        if e["relation"] == "covered":
            continue
        required_level = e.get("level", 3)
        # Gap degree: missing -> 1.0 - coverage; partial -> 0.5 - something.
        gap_degree = round(1.0 - e["coverage"], 2)
        # Priority: bigger gap or hard requirement -> higher.
        if gap_degree >= _GAP_LOW or e["category"] == "hard":
            priority = "high"
        elif gap_degree >= _GAP_HIGH:
            priority = "medium"
        else:
            priority = "low"

        current_evidence = _collect_evidence(e["ability"], unfolded, experiences)

        why = ""
        evidence = ""
        improvement_direction = ""
        if ai_status == "ok":
            try:
                r = gateway.run(
                    "f11_gap_explain",
                    {
                        "ability": e["ability"],
                        "required_level": required_level,
                        "current_evidence": current_evidence,
                        "gap_degree": gap_degree,
                        "priority": priority,
                    },
                )
                why = r.data.get("why", "")
                evidence = r.data.get("evidence", "")
                improvement_direction = r.data.get("improvement_direction", "")
            except AIGatewayError:
                why = "AI 解释暂不可用，请稍后重试或手动补充判断。"
                evidence = "；".join(current_evidence) or "暂无明确证据"
                improvement_direction = "建议结合岗位要求通过项目实践或系统学习补齐。"

        gap_rows.append({
            "ability": e["ability"],
            "current_evidence": current_evidence,
            "required_level": required_level,
            "gap_degree": gap_degree,
            "priority": priority,
            "why": why,
            "evidence": evidence,
            "improvement_direction": improvement_direction,
            "status": "open",
        })

    return replace_gaps(db, user_id=user_id, match_id=match_id, gaps=gap_rows)


def _collect_evidence(ability: str, unfolded: dict, experiences: list) -> list[str]:
    """Gather profile + experience evidence mentioning the ability (program side)."""
    ev: list[str] = []
    tags = unfolded.get("ability_tags", []) or []
    strengths = unfolded.get("strengths", []) or []
    hay = " ".join([ability] + tags + strengths)
    for t in tags:
        if t and (t in ability or ability in t):
            ev.append(f"能力标签：{t}")
    for s in strengths:
        if s and (s in ability or ability in s):
            ev.append(f"优势：{s}")
    for e in experiences:
        title = e.get("title", "")
        detail = e.get("detail", "")
        if ability in title or ability in detail:
            ev.append(f"经历：{title}")
    return ev[:5]


def _keyword_relation(name: str, unfolded: dict, experiences: list) -> dict:
    """Program fallback relation when AI didn't judge this ability."""
    tags = set(unfolded.get("ability_tags", []) or [])
    strengths = set(unfolded.get("strengths", []) or [])
    exp_text = " ".join(f"{e.get('title','')} {e.get('detail','')}" for e in experiences)
    hay = " ".join([name] + list(tags) + list(strengths))
    if name and (name in hay or name in exp_text):
        relation = "covered"
    elif name and any(name in t or t in name for t in (tags | strengths)):
        relation = "partial"
    else:
        relation = "missing"
    return {
        "ability": name, "relation": relation,
        "reason": "（AI 暂不可用，已用关键词匹配做近似判断，精确度较低）",
        "evidence": "基于画像能力标签与经历关键词匹配",
    }


# ----------------------------- dict helpers -----------------------------
def _match_to_dict(match) -> dict:
    return {
        "match_id": match.id,
        "target_job_id": match.target_job_id,
        "profile_version": match.profile_version,
        "jd_version": match.jd_version,
        "total_score": match.total_score,
        "dimension_scores": match.dimension_scores or [],
        "strengths": match.strengths or [],
        "risks": match.risks or [],
        "relation_judgements": match.relation_judgements or [],
        "ai_status": match.ai_status,
        "created_at": match.created_at.isoformat() if match.created_at else None,
        "updated_at": match.updated_at.isoformat() if match.updated_at else None,
    }


def _gap_to_dict(gap) -> dict:
    return {
        "gap_id": gap.id,
        "match_id": gap.match_id,
        "ability": gap.ability,
        "current_evidence": gap.current_evidence or [],
        "required_level": gap.required_level,
        "gap_degree": gap.gap_degree,
        "priority": gap.priority,
        "why": gap.why,
        "evidence": gap.evidence,
        "improvement_direction": gap.improvement_direction,
        "status": gap.status,
        "created_at": gap.created_at.isoformat() if gap.created_at else None,
    }
