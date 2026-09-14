"""Deterministic Explore recommender (Phase 2).

This module is the PROGRAM side of Explore. It owns everything that must be
explainable, testable and offline-capable:

  * candidate direction filtering (against the knowledge base)
  * preference / ability / interest / experience matching
  * deterministic 0..1 match score
  * human-readable match basis (why this score)
  * exclusion of "not interested" directions
  * compare metrics

The AI (F4) only later writes a warm ``reason`` paragraph on top of this.
No scores, rankings or conclusions are ever produced by the AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.explore import Direction


@dataclass
class UserSignal:
    """Flattened view of the user the recommender cares about.

    Built by the explore service from career_profile + experiences + preferences.
    """

    ability_tags: list[str] = field(default_factory=list)
    interest_tags: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    positioning: str = ""
    # Structured exploration preferences (program-parsed from natural language).
    preferences: dict = field(default_factory=dict)
    # Direction ids the user excluded.
    excluded_direction_ids: list[int] = field(default_factory=list)


def _contains_any(haystack: list[str], needles: list[str]) -> list[str]:
    """Return the subset of needles found (case-insensitive) in haystack."""
    hay = [h.lower() for h in haystack]
    out: list[str] = []
    for n in needles:
        if n and n.lower() in hay:
            out.append(n)
    return out


def _overlap(a: list[str], b: list[str]) -> list[str]:
    """Case-insensitive overlap of two tag lists (returns matched items from b)."""
    low_a = {x.lower() for x in a}
    return [y for y in b if y and y.lower() in low_a]


def score_direction(direction: Direction, sig: UserSignal) -> tuple[float, list[str]]:
    """Compute a deterministic 0..1 match score + human-readable basis.

    Signal weights (sum normalizes later):
      * ability overlap with core_abilities ................. 0.35
      * interest overlap with direction themes .............. 0.20
      * strength overlap with core_abilities ................ 0.15
      * preference field match (industry/avoid) ............. 0.20
      * attribute affinity (growth/stability/autonomy/social) 0.10
    """
    basis: list[str] = []
    raw = 0.0

    # 1) Ability overlap
    ability_hits = _overlap(sig.ability_tags, direction.core_abilities)
    if ability_hits:
        w = min(len(ability_hits) / max(len(direction.core_abilities), 1), 1.0) * 0.35
        raw += w
        basis.append(f"你的能力「{ability_hits[0]}」与该方向的核心能力匹配")

    # 2) Interest overlap (direction themes = name/summary/industries jobs)
    themes = [direction.name, direction.summary] + direction.work_styles + direction.core_abilities
    interest_hits = _overlap(sig.interest_tags, themes)
    if interest_hits:
        raw += min(len(interest_hits) / 3.0, 1.0) * 0.20
        basis.append(f"你对「{interest_hits[0]}」的兴趣与该方向相关")

    # 3) Strength overlap
    strength_hits = _overlap(sig.strengths, direction.core_abilities)
    if strength_hits:
        raw += min(len(strength_hits) / 2.0, 1.0) * 0.15
        basis.append(f"你的优势「{strength_hits[0]}」在该方向能发挥作用")

    # 4) Preference: preferred fields (industries) and avoid keywords
    prefs = sig.preferences or {}
    prefer_fields = [str(x) for x in (prefs.get("prefer_fields") or [])]
    avoid_keywords = [str(x).lower() for x in (prefs.get("avoid_keywords") or [])]
    # Field match: compare direction's industries' slugs/names to prefer_fields.
    # (industry names are supplied by the caller via direction.industry_ids; here
    #  we approximate using work_styles + core_abilities text contains.)
    direction_text = " ".join(
        [direction.name, direction.summary, direction.description]
        + direction.core_abilities + direction.work_styles
    ).lower()
    if prefer_fields:
        if any(f.lower() in direction_text for f in prefer_fields):
            raw += 0.20
            basis.append(f"符合你倾向的领域「{prefer_fields[0]}」")
    if avoid_keywords:
        if any(k in direction_text for k in avoid_keywords):
            raw -= 0.40
            basis.append(f"包含你明确不想做的要素「{avoid_keywords[0]}」")
    # City / stability / growth value nudges
    if prefs.get("value_stability") and direction.attributes.get("stability", 0) >= 0.7:
        raw += 0.05
        basis.append("该方向相对稳定，符合你看重稳定的偏好")
    if prefs.get("value_growth") and direction.attributes.get("growth", 0) >= 0.7:
        raw += 0.05
        basis.append("该方向成长空间较大，符合你看重成长偏好")

    # 5) Attribute affinity (only if we already have some positive signal)
    if raw > 0:
        attr = direction.attributes or {}
        # mild bonus for autonomy/social depending on preference hints (kept small)
        if prefs.get("value_autonomy") and attr.get("autonomy", 0) >= 0.65:
            raw += 0.05
        if prefs.get("value_social") and attr.get("social", 0) >= 0.7:
            raw += 0.05

    score = max(0.0, min(1.0, raw))
    if not basis:
        basis.append("与你的画像暂无强匹配信号，可作为了解项")
    return round(score, 3), basis


def rank_directions(directions: list[Direction], sig: UserSignal) -> list[tuple[Direction, float, list[str]]]:
    """Score + sort all directions; excluded ones are flagged but still returned
    (the service decides whether to surface them)."""
    scored = [(*score_direction(d, sig), d) for d in directions]
    # sort by score desc
    scored.sort(key=lambda t: t[1], reverse=True)
    return [(d, s, b) for (s, b, d) in scored]


def build_compare_rows(
    directions: list[Direction], sig: UserSignal
) -> list[dict]:
    """Build comparable rows for the compare view (program-computed metrics)."""
    rows = []
    for d in directions:
        score, _ = score_direction(d, sig)
        rows.append({
            "direction_id": d.id,
            "name": d.name,
            "summary": d.summary,
            "score": score,
            "work_styles": d.work_styles,
            "core_abilities": d.core_abilities,
            "attributes": d.attributes,
            "not_good_for": d.not_good_for,
            "growth_path": d.growth_path,
        })
    return rows


def compare_advice(rows: list[dict]) -> list[str]:
    """Generate neutral, decision-support advice (NOT a ranking verdict).

    Tells the user *under which value each direction is stronger*, instead of
    declaring a winner. This honors "help decide, don't decide for them".
    """
    if len(rows) < 2:
        return []
    advice: list[str] = []
    # highest growth vs highest stability
    by_growth = max(rows, key=lambda r: r["attributes"].get("growth", 0))
    by_stability = max(rows, key=lambda r: r["attributes"].get("stability", 0))
    if by_growth["name"] != by_stability["name"]:
        advice.append(
            f"如果你更看重成长空间，「{by_growth['name']}」更突出；"
            f"如果你更看重稳定，「{by_stability['name']}」更合适。"
        )
    by_social = max(rows, key=lambda r: r["attributes"].get("social", 0))
    by_auto = max(rows, key=lambda r: r["attributes"].get("autonomy", 0))
    if by_social["name"] != by_auto["name"]:
        advice.append(
            f"如果你偏好与人高频协作，可看「{by_social['name']}」；"
            f"如果你更想独立钻研，「{by_auto['name']}」更匹配。"
        )
    return advice
