"""Decision service (Phase 6: F21 维度映射 / F22 权重 / F23 综合评分).

Pure, deterministic. The program owns EVERY score / rank / weight. The AI never
computes or emits any of them.

Dimension model (fixed 4 non-economic + 2 economic, aligned across F21/F22/F23):
  economic    -- annual after-tax income (定量, 相对归一化)
  disposable  -- annual disposable income after city cost (定量, 相对归一化)
  workload     -- 工作强度 (0-100, user/match; higher = better=less intense)
  stability    -- 稳定性 (0-100, user/match)
  growth       -- 发展空间 (0-100, user/match)
  match        -- 岗位匹配度 (0-100, from target_job match_result or user)

F23 composite (relative normalization):
  * Quantitative dims (economic, disposable): highest value in the comparison
    set maps to 100; others scale proportionally. (higher is better)
  * Qualitative dims (workload/stability/growth/match): use the user/match score
    directly (already 0-100). Missing -> excluded from that offer's weighting.
  * composite = Σ(dim_score × weight) / Σ(active_weights)
  * rank = composite desc; ties broken by the highest-weighted dim score.

Weights are RELATIVE (no normalization required); default preset "balanced".
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.errors.exceptions import ValidationError_ as AppValidationError
from app.models.offer import Offer
from app.repositories_offer import (
    get_decision_weight,
    get_dimensions,
    get_offer,
    get_offers,
    save_score_results,
    upsert_decision_weight,
    upsert_dimension,
)

# Fixed non-economic dimensions (F21, 4 个).
NON_ECONOMIC = ["workload", "stability", "growth", "match"]
ALL_DIMENSIONS = ["economic", "disposable"] + NON_ECONOMIC

DIMENSION_LABELS = {
    "economic": "经济收益",
    "disposable": "可支配收入",
    "workload": "工作强度",
    "stability": "稳定性",
    "growth": "发展空间",
    "match": "岗位匹配度",
}

# Preset weight schemes (relative; need not sum to 100).
PRESETS = {
    "balanced": {"economic": 25, "disposable": 20, "workload": 15, "stability": 15, "growth": 15, "match": 10},
    "salary": {"economic": 40, "disposable": 30, "workload": 10, "stability": 5, "growth": 10, "match": 5},
    "stability": {"economic": 15, "disposable": 10, "workload": 15, "stability": 35, "growth": 15, "match": 10},
    "growth": {"economic": 15, "disposable": 10, "workload": 10, "stability": 10, "growth": 40, "match": 15},
}

DEFAULT_WEIGHTS = PRESETS["balanced"]


# ----------------------------- F22 权重 -----------------------------
def get_weights(db: Session, *, user_id: int) -> dict:
    row = get_decision_weight(db, user_id)
    if row is None:
        return {"weights": dict(DEFAULT_WEIGHTS), "preset_name": None}
    return {"weights": row.weights or dict(DEFAULT_WEIGHTS), "preset_name": row.preset_name}


def save_weights(db: Session, *, user_id: int, weights: dict,
                 preset_name: str | None = None) -> dict:
    cleaned = {}
    for dim in ALL_DIMENSIONS:
        v = weights.get(dim)
        if v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise AppValidationError(f"权重 {dim} 必须为数字", code="invalid_weight")
            if v < 0:
                raise AppValidationError(f"权重 {dim} 不能为负", code="invalid_weight")
            cleaned[dim] = v
    # preset_name: if a known preset and weights match, record it; else custom.
    if preset_name and preset_name in PRESETS:
        pass
    elif preset_name is None and _matches_preset(cleaned):
        preset_name = _matches_preset(cleaned)
    row = upsert_decision_weight(db, user_id=user_id, weights=cleaned, preset_name=preset_name)
    db.commit()
    return {"weights": row.weights, "preset_name": row.preset_name}


def _matches_preset(weights: dict) -> str | None:
    for name, preset in PRESETS.items():
        if all(abs(weights.get(d, 0) - preset.get(d, 0)) < 1e-6 for d in ALL_DIMENSIONS):
            return name
    return None


# ----------------------------- F21 维度评分存储 -----------------------------
def save_dimension_scores(db: Session, *, user_id: int, offer_id: int,
                          scores: dict) -> dict:
    """Persist user-confirmed dimension scores (0-100). Only the 4 fixed
    non-economic dims are user-editable here; economic/disposable are derived."""
    offer = get_offer(db, user_id, offer_id)
    if offer is None:
        raise AppValidationError("Offer 不存在", code="not_found")
    saved = {}
    for dim in NON_ECONOMIC:
        v = scores.get(dim)
        if v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise AppValidationError(f"维度 {dim} 分数必须为整数", code="invalid_score")
            if not (0 <= v <= 100):
                raise AppValidationError(f"维度 {dim} 分数必须在 0-100", code="invalid_score")
            upsert_dimension(db, offer_id=offer_id, dimension=dim, score=v,
                             evidence=None, source="user")
            saved[dim] = v
    db.commit()
    return {"offer_id": offer_id, "scores": saved}


# ----------------------------- F23 综合评分 -----------------------------
def compute_comparison(db: Session, *, user_id: int, offer_ids: list[int] | None = None,
                       weights: dict | None = None,
                       computed: dict[int, dict] | None = None) -> dict:
    """Compute the deterministic composite comparison for the user's offers.

    Only ``active`` / ``accepted`` offers participate (PRD 8.2.2). If offer_ids
    is given, restrict to that subset (still must belong to the user).

    ``computed`` supplies the quantitative dimensions that are NOT stored in
    ``offer_dimension`` (which only holds the four user-confirmed qualitative
    scores). It maps ``offer_id -> {"economic": float, "disposable": float}``,
    produced by the caller from the persisted salary calc + city cost
    (see ``analysis_service.run_decision_analysis``). Omitting it keeps the
    previous behavior: quantitative dims are treated as unknown and excluded
    from the weighted average.

    Returns:
      {comparison_id, offers:[{offer_id, company, job_title, city, status,
       dimension_scores, composite_score, rank, salary_summary, cost_summary}],
       weights, weight_snapshot, calc_version}
    """
    if weights is None:
        weights = get_weights(db, user_id=user_id)["weights"]

    # Pull offers.
    if offer_ids:
        offers = [get_offer(db, user_id, oid) for oid in offer_ids]
        offers = [o for o in offers if o is not None]
    else:
        offers = [o for o in get_offers(db, user_id) if o.status in ("active", "accepted")]

    if not offers:
        return {
            "comparison_id": str(uuid.uuid4())[:12],
            "offers": [], "weights": weights, "weight_snapshot": weights,
            "calc_version": "2024",
        }

    # Gather per-offer computed inputs.
    computed = computed or {}
    rows = []
    for o in offers:
        # offer_dimension holds ONLY the four user-confirmed qualitative scores
        # (AI never writes a number there -- it writes ai_dimension_reference tiers).
        dims = {d.dimension: d.score for d in get_dimensions(db, o.id)}
        extra = computed.get(o.id) or {}
        rows.append({
            "offer": o,
            "dim_scores": dims,
            "economic": extra.get("economic"),
            "disposable": extra.get("disposable"),
        })

    return _finalize_comparison(db, user_id=user_id, rows=rows, weights=weights)



def _finalize_comparison(db, *, user_id: int, rows: list[dict], weights: dict) -> dict:
    """Internal: normalize + weight + rank. Economic/disposable are expected in
    each row as `row['economic']` / `row['disposable']` (precomputed by API)."""
    # Find maxima for quantitative normalization.
    econ_vals = [r.get("economic") for r in rows if r.get("economic") is not None]
    disp_vals = [r.get("disposable") for r in rows if r.get("disposable") is not None]
    econ_max = max(econ_vals) if econ_vals else 0.0
    disp_max = max(disp_vals) if disp_vals else 0.0

    results = []
    for r in rows:
        o: Offer = r["offer"]
        dim_scores = r.get("dim_scores", {})
        # Build full 6-dim score vector with relative normalization.
        full = {}
        # economic
        if r.get("economic") is not None and econ_max > 0:
            full["economic"] = round(r["economic"] / econ_max * 100, 2)
        elif r.get("economic") is not None:
            full["economic"] = 100.0
        else:
            full["economic"] = None
        # disposable
        if r.get("disposable") is not None and disp_max > 0:
            full["disposable"] = round(r["disposable"] / disp_max * 100, 2)
        elif r.get("disposable") is not None:
            full["disposable"] = 100.0
        else:
            full["disposable"] = None
        # qualitative (already 0-100 or None)
        for dim in NON_ECONOMIC:
            full[dim] = dim_scores.get(dim)

        # Composite = Σ(score×w) / Σ(active_w). Skip dims with None score.
        num = 0.0
        den = 0.0
        for dim in ALL_DIMENSIONS:
            s = full.get(dim)
            w = weights.get(dim, 0) or 0
            if s is not None and w > 0:
                num += s * w
                den += w
        composite = round(num / den, 2) if den > 0 else 0.0

        results.append({
            "offer_id": o.id,
            "company": o.company,
            "job_title": o.job_title,
            "city": o.city,
            "status": o.status,
            "dimension_scores": full,
            "composite_score": composite,
        })

    # Rank: composite desc; tie-break by highest-weighted dim score.
    def _tiebreak(rr):
        best = -1.0
        for dim in ALL_DIMENSIONS:
            w = weights.get(dim, 0) or 0
            s = rr["dimension_scores"].get(dim)
            if s is not None and w > 0:
                best = max(best, s * w)
        return best
    results.sort(key=lambda x: (x["composite_score"], _tiebreak(x)), reverse=True)
    for i, rr in enumerate(results, 1):
        rr["rank"] = i

    comparison_id = str(uuid.uuid4())[:12]
    save_score_results(db, comparison_id=comparison_id, results=[
        {
            "offer_id": rr["offer_id"],
            "composite_score": rr["composite_score"],
            "dimension_scores": rr["dimension_scores"],
            "rank": rr["rank"],
            "weight_snapshot": weights,
        }
        for rr in results
    ])
    db.commit()

    return {
        "comparison_id": comparison_id,
        "offers": results,
        "weights": weights,
        "weight_snapshot": weights,
        "calc_version": "2024",
    }
