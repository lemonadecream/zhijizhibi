"""Analysis service (Phase 6: F21 定性评估 / F24 AI 分析).

F21: the AI judges the four fixed non-economic dimensions into tiers; the program
maps tier -> 0-100 and stores the result. The model never emits a score.

F24: the program injects the FULL deterministic comparison (scores / ranks /
costs) into the prompt; the AI only writes focused, conditional, non-absolute
analysis. It must never recompute numbers; business validation + the gateway
reject any leaked/conflicting figure.

Design rules:
  * Program owns every number. The gateway is the ONLY AI entry point.
  * On AI failure, the panel still renders via deterministic fallback.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.gateway import get_gateway
from app.ai.schemas import TIER_TO_SCORE
from app.errors.exceptions import ValidationError_ as AppValidationError
from app.models.offer import Offer
from app.repositories_offer import (
    get_ai_reference,
    get_dimensions,
    get_offer,
    save_decision_analysis,
    upsert_ai_reference,
)
from app.services.decision_service import (
    ALL_DIMENSIONS,
    DIMENSION_LABELS,
    compute_comparison,
    get_weights,
)
from app.services.cost_service import resolve_city_cost
from app.services.salary_service import build_param_snapshot, compute_salary


# ----------------------------- F21: qualitative assessment -----------------------------
def run_dimension_assessment(db: Session, *, user_id: int, offer_id: int,
                              public_signals: list[str] | None = None,
                              user_notes: str = "") -> dict:
    """Invoke F21 for the four fixed dimensions. Always persists an AI reference
    row (even on fallback) so the offer card has stable qualitative context."""
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise AppValidationError("Offer 不存在", code="not_found")

    target_match = None
    if offer.target_job_id:
        # Optional: pull match_result payload from the target_job table if present.
        tj = db.get(Offer.__mapper__.class_registry.get("TargetJob"), offer.target_job_id) if False else None
        # Keep it simple/safe: we do not couple to target_job internals here.
        target_match = None

    gateway = get_gateway()
    result = gateway.run("f21_dimension_assess", {
        "company": offer.company,
        "job_title": offer.job_title,
        "city": offer.city or "",
        "public_signals": public_signals or [],
        "user_notes": user_notes or offer.note or "",
        "target_job_match": target_match,
    })

    assessments = result.data.get("assessments", [])
    saved = {}
    for a in assessments:
        dim = a["dimension"]
        upsert_ai_reference(
            db, offer_id=offer_id, dimension=dim,
            judgement=a["tier"], evidence=a.get("evidence"),
            info_source="ai" if result.status == "ok" else "fallback",
        )
        saved[dim] = {
            "dimension": dim,
            "label": DIMENSION_LABELS.get(dim, dim),
            "tier": a["tier"],
            "score": TIER_TO_SCORE.get(a["tier"], 55),
            "reason": a.get("reason", ""),
            "source": result.status,
        }
    db.commit()
    return {"offer_id": offer_id, "assessments": saved, "ai_status": result.status}


# ----------------------------- F24: decision analysis -----------------------------
def run_decision_analysis(db: Session, *, user_id: int, offer_ids: list[int] | None = None,
                          weights: dict | None = None, extra_context: str = "") -> dict:
    """Run F24 against the PROGRAM-computed comparison. The AI only explains.

    Returns {
      comparison_id, offers (with composite + dimension_scores + rank),
      weights, weight_snapshot, city_costs, analysis:{recommendations, ai_status}
    }
    """
    comp = compute_comparison(db, user_id=user_id, offer_ids=offer_ids, weights=weights)
    comparison_id = comp["comparison_id"]
    offers = comp["offers"]
    weights = comp["weights"]
    weight_snapshot = comp["weight_snapshot"]

    # Build city cost map for injected context.
    city_costs = {}
    for o in offers:
        if o.get("city"):
            resolved = resolve_city_cost(db, user_id=user_id, city=o["city"])
            city_costs[o["city"]] = {
                "monthly_total": resolved["monthly_total"],
                "annual_total": resolved["monthly_total"] * 12,
            }

    gateway = get_gateway()
    result = gateway.run("f24_decision_analysis", {
        "offers": [
            {
                "company": o["company"],
                "job_title": o["job_title"],
                "city": o.get("city"),
                "composite_score": o["composite_score"],
                "dimension_scores": o["dimension_scores"],
                "rank": o.get("rank"),
            }
            for o in offers
        ],
        "weights": weights,
        "weight_snapshot": weight_snapshot,
        "city_costs": city_costs,
        "extra_context": extra_context,
    })

    analysis = {
        "recommendations": result.data.get("recommendations", []),
        "ai_status": result.status,
        "error": result.error,
    }
    save_decision_analysis(
        db, comparison_id=comparison_id, user_id=user_id,
        content_json=analysis, data_snapshot={"offers": offers, "city_costs": city_costs},
        model_version="2024",
    )
    db.commit()

    return {
        "comparison_id": comparison_id,
        "offers": offers,
        "weights": weights,
        "weight_snapshot": weight_snapshot,
        "city_costs": city_costs,
        "analysis": analysis,
    }
