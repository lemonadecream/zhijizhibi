"""Input / output schemas for AI tasks (F1, F2).

Pydantic models are the single source of truth for structure. The gateway uses
them both for input validation and for LLM output validation (JSON-Schema
equivalent). Business-only rules (e.g. risk must carry a strategy) live in the
task's ``validate_business`` hook.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ----------------------------- F1: resume / experience parsing -----------------------------
class F1Education(BaseModel):
    school: str
    major: str
    degree: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class F1Internship(BaseModel):
    company: str
    role: str
    start: Optional[str] = None
    end: Optional[str] = None
    duty: Optional[str] = None


class F1Project(BaseModel):
    name: str
    role: Optional[str] = None
    desc: Optional[str] = None


class F1Skill(BaseModel):
    name: str
    level: Optional[int] = Field(default=None, ge=1, le=5)


class F1Signal(BaseModel):
    type: str  # preference / strength_hint / risk_hint ...
    text: str
    evidence: str


class F1Output(BaseModel):
    education: list[F1Education] = Field(default_factory=list)
    internships: list[F1Internship] = Field(default_factory=list)
    projects: list[F1Project] = Field(default_factory=list)
    skills: list[F1Skill] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    signals: list[F1Signal] = Field(default_factory=list)


class F1Input(BaseModel):
    # The text to structure. May be extracted resume text or free-form text.
    raw_text: str = Field(min_length=1, max_length=20000)


# ----------------------------- F2: career profile generation -----------------------------
class AbilityTag(BaseModel):
    tag: str
    level: Optional[int] = Field(default=None, ge=1, le=5)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence: str = ""


class InterestTag(BaseModel):
    tag: str
    evidence: str = ""


class Strength(BaseModel):
    item: str
    evidence: str


class Risk(BaseModel):
    item: str
    evidence: str
    strategy: str


class Tendency(BaseModel):
    """A visual career tendency axis (e.g. 探索性 / 稳定性), 0..1 normalized.

    The program renders these as labelled horizontal bars; the AI only supplies
    the raw leaning (never a 0-100 'score'). ``confidence`` reflects how sure the
    AI is given the available evidence.
    """

    axis: str
    leaning: float = Field(ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    note: str = ""


class Gap(BaseModel):
    """Something the person may still need to build -- the warmer sibling of 'risk'.

    Replaces the old 'risks' framing. ``why`` explains the AI's reasoning so the
    user understands the judgment instead of being judged.
    """

    item: str
    why: str
    evidence: str = ""


class F2Output(BaseModel):
    # --- Phase 1B additions (all optional for backward compatibility) ---
    positioning: str = ""  # one AI-written sentence summarizing who this person is
    tendencies: list[Tendency] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    career_goal: Optional[str] = None  # user-stated goal, echoed/refined by AI

    # --- Legacy fields (kept for backward-compat with existing callers) ---
    ability_tags: list[AbilityTag] = Field(default_factory=list)
    interest_tags: list[InterestTag] = Field(default_factory=list)
    strengths: list[Strength] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    preference_infer: dict = Field(default_factory=dict)

    @field_validator("risks")
    @classmethod
    def _risks_have_strategy(cls, v):
        for r in v:
            if not r.strategy or not r.strategy.strip():
                raise ValueError("every risk must carry a non-empty strategy")
        return v


class F2ExperienceItem(BaseModel):
    type: str  # education / internship / project / skill
    title: str
    detail: str = ""


class F2Input(BaseModel):
    # Structured, user-confirmed experiences (already saved, not raw resume).
    experiences: list[dict] = Field(default_factory=list)
    career_goal: Optional[dict] = None
    preference: Optional[dict] = None
    # Phase 1B: the interview understanding, corrections and stated goal, folded
    # into the generation context (never replaces the experiences as ground truth).
    interview_context: Optional[dict] = None


# ----------------------------- Interview step (Phase 1B) -----------------------------
# The six interview dimensions. The AI probes naturally across them; the user
# never sees a "please fill in dimension X" prompt.
DIMENSIONS = ["D1", "D2", "D3", "D4", "D5", "D6"]
DIMENSION_LABELS = {
    "D1": "经历",
    "D2": "能力",
    "D3": "兴趣",
    "D4": "性格 / 工作方式",
    "D5": "价值观 / 动机",
    "D6": "求职意向",
}


class InterviewDimensionState(BaseModel):
    dimension: str  # D1..D6
    covered: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    note: str = ""


class InterviewUnderstanding(BaseModel):
    """The AI's progressive 'what I know about you' snapshot.

    Rendered in the side panel as tags + short sentences -- never as a DB table.
    """

    tags: list[str] = Field(default_factory=list)  # e.g. ["有产品实践经验", "喜欢分析问题"]
    sentences: list[str] = Field(default_factory=list)  # short natural-language notes
    evidence: dict = Field(default_factory=dict)  # tag/piece -> source snippet


# ----------------------------- F4: direction reason (Explore) -----------------------------
# The ONLY AI-authored field in Explore. The program computes the score, the
# ranked candidate list and the match basis; the AI merely writes a warm,
# personal "why this direction fits your profile" paragraph. It must NOT emit
# any numeric score / match percentage / salary — that is the program's job.
class F4Input(BaseModel):
    # The direction's knowledge-base facts (program-supplied, never invented).
    direction_name: str = ""
    direction_summary: str = ""
    direction_core_abilities: list[str] = Field(default_factory=list)
    direction_work_styles: list[str] = Field(default_factory=list)
    # The user's profile highlights (program-supplied).
    user_positioning: str = ""
    user_ability_tags: list[str] = Field(default_factory=list)
    user_interest_tags: list[str] = Field(default_factory=list)
    user_strengths: list[str] = Field(default_factory=list)
    # The deterministic match basis the program already computed (for context).
    match_basis: list[str] = Field(default_factory=list)


class F4Output(BaseModel):
    # A 1-3 sentence, second-person, warm explanation of why this direction fits.
    # The AI should reference the user's actual profile highlights, not flatter.
    reason: str = ""


class InterviewStepInput(BaseModel):
    # How this session started: "upload" | "paste" | "scratch"
    entry_method: str = "scratch"
    # Confirmed experiences captured at interview start (context for the AI).
    experiences: list[dict] = Field(default_factory=list)
    # Full conversation so far (most recent last): [{"role","text"}].
    history: list[dict] = Field(default_factory=list)
    # Current dimension coverage + confidence.
    dimension_state: list[InterviewDimensionState] = Field(default_factory=list)
    # Current understanding snapshot.
    understanding: InterviewUnderstanding = Field(default_factory=InterviewUnderstanding)
    # Open follow-up prompts the AI still wants to ask.
    wants_to_know: list[str] = Field(default_factory=list)
    # The user's latest message (already appended to history by the caller).
    latest_message: str = Field(default="", max_length=4000)


class InterviewStepOutput(BaseModel):
    # 1~2 sentences of natural, warm acknowledgement + a single core question.
    # Max 2 questions -- never a questionnaire.
    response: str = ""
    questions: list[str] = Field(default_factory=list)  # 1..2 questions
    # Updated snapshots (the AI revises these each turn):
    understanding: InterviewUnderstanding = Field(default_factory=InterviewUnderstanding)
    wants_to_know: list[str] = Field(default_factory=list)
    dimension_state: list[InterviewDimensionState] = Field(default_factory=list)
    # Whether the six dimensions have reached minimum completeness.
    completion_ready: bool = False
    # If completion_ready, a short candidate summary to confirm with the user.
    summary_candidate: str = ""


# ----------------------------- F9: JD parse (Phase 3 Target Job) -----------------------------
# The AI extracts a STRUCTURED ability model from a free-text JD. It must NOT
# invent requirements not present in the JD. The program owns validation, the
# weight / level semantics, and all scoring.
class F9Ability(BaseModel):
    name: str
    category: str  # hard / soft / plus (requirement_type)
    level: int = Field(default=3, ge=1, le=5)  # 1-5 required proficiency
    weight: float = Field(default=1.0, ge=0.0, le=2.0)  # program-readable importance
    requirement_type: str = ""  # hard / soft / plus (mirrors category, kept explicit)


class F9Requirements(BaseModel):
    education: str = ""  # e.g. "本科及以上"
    experience_years: int = 0
    major: list[str] = Field(default_factory=list)
    cert: list[str] = Field(default_factory=list)


class F9Output(BaseModel):
    company: str = ""
    title: str = ""
    industry: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    abilities: list[F9Ability] = Field(default_factory=list)
    requirements: F9Requirements = Field(default_factory=F9Requirements)
    other_requirements: list[str] = Field(default_factory=list)


class F9Input(BaseModel):
    raw_jd: str = Field(min_length=1, max_length=20000)
    job_title: str = ""
    company: str = ""
    city: str = ""


# ----------------------------- F10: match judgement (Phase 3 Target Job) -----------------------------
# The AI ONLY judges the semantic relation between the user's profile and each
# required ability. It MUST NOT output any numeric score / match percentage /
# salary. The program maps relation -> coverage and computes the final score.
class F10Judgement(BaseModel):
    ability: str
    relation: str  # covered | partial | missing
    reason: str = ""  # why this relation holds (semantic explanation)
    evidence: str = ""  # which profile/experience item supports the judgement


class F10Output(BaseModel):
    judgements: list[F10Judgement] = Field(default_factory=list)


class F10Input(BaseModel):
    # Program-supplied, never invented by the model.
    profile_ability_tags: list[str] = Field(default_factory=list)
    profile_strengths: list[str] = Field(default_factory=list)
    experiences: list[dict] = Field(default_factory=list)
    ability_model: dict = Field(default_factory=dict)  # target_job.ability_model


# ----------------------------- F11: gap explanation (Phase 3 Target Job) -----------------------------
# The AI ONLY explains a gap that the program already identified. It MUST NOT
# compute a gap score / priority -- the program owns those numbers.
class F11Output(BaseModel):
    why: str = ""  # why this is a gap (semantic explanation)
    evidence: str = ""  # what currently supports / fails to support the requirement
    improvement_direction: str = ""  # how to close it (hint, not a prescription)


class F11Input(BaseModel):
    # Program-supplied gap context (the program already decided degree/priority).
    ability: str = ""
    required_level: int | None = None
    current_evidence: list[str] = Field(default_factory=list)
    gap_degree: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: str = "medium"


# ----------------------------- F12: preparation plan (Phase 4) -----------------------------
# The AI CONVERTS Phase 3 gaps into human, actionable preparation advice. It must
# NOT compute a priority (the program copies it from the gap) or any score /
# completion / number. It only writes: why prepare (reason) + how (action).
class F12PrepItem(BaseModel):
    ability: str = ""  # which gap ability this task addresses (program key)
    title: str = ""  # short, actionable task title
    reason: str = ""  # why this prep matters (semantic explanation)
    action_suggestion: str = ""  # concrete how-to (hint, not prescription)


class F12Output(BaseModel):
    prep_items: list[F12PrepItem] = Field(default_factory=list)


class F12Input(BaseModel):
    # Program-supplied context (never invented by the model).
    job_title: str = ""
    company: str = ""
    # Phase 3 gaps (single source of truth) -- ability / priority / why / evidence.
    gaps: list[dict] = Field(default_factory=list)


# ----------------------------- F14: interview focus (Phase 4) -----------------------------
# The AI proposes likely interview questions for THIS target job, each grounded
# in a JD requirement and, where possible, a real user experience. It must NOT
# output any score / number. ``evidence_status`` is program-derived, not AI.
class F14FocusItem(BaseModel):
    question: str = ""  # the likely question / topic
    reason: str = ""  # why this might be asked
    related_requirement: str = ""  # which JD ability / requirement it maps to
    related_experience: str = ""  # which real user experience can answer it
    preparation_advice: str = ""  # how to prepare an answer
    evidence_status: str = "none"  # sufficient | insufficient | none (AI may hint)


class F14Output(BaseModel):
    focus_items: list[F14FocusItem] = Field(default_factory=list)


class F14Input(BaseModel):
    # Program-supplied, never invented.
    job_title: str = ""
    company: str = ""
    abilities: list[dict] = Field(default_factory=list)  # target_job.ability_model.abilities
    responsibilities: list[str] = Field(default_factory=list)
    gaps: list[dict] = Field(default_factory=list)  # partial / missing abilities
    profile_positioning: str = ""
    ability_tags: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    experiences: list[dict] = Field(default_factory=list)


# ----------------------------- F13: resume advice (Phase 4, P1) -----------------------------
# The AI gives lightweight, targeted resume tweaks for THIS target job. It must
# NOT rewrite the whole resume or output any score. ``severity`` is program-owned.
class F13Advice(BaseModel):
    advice_type: str = ""  # highlight | evidence_gap | keyword | weak_link
    content: str = ""  # the suggestion
    related_experience: str = ""  # which experience to act on (if any)
    related_gap: str = ""  # which gap ability it relates to (if any)
    severity: str = "medium"  # high | medium | low (AI may hint)


class F13Output(BaseModel):
    advices: list[F13Advice] = Field(default_factory=list)


class F13Input(BaseModel):
    # Program-supplied, never invented.
    job_title: str = ""
    company: str = ""
    strengths: list[dict] = Field(default_factory=list)  # match strengths
    risks: list[dict] = Field(default_factory=list)  # match risks
    gaps: list[dict] = Field(default_factory=list)
    ability_tags: list[str] = Field(default_factory=list)
    experiences: list[dict] = Field(default_factory=list)


# ----------------------------- F21: qualitative dimension assessment (Phase 6 Offer) -----------------------------
# The AI ONLY judges the four fixed non-economic dimensions (workload / stability
# / growth / match) into a tier + explanation. It MUST NOT output a numeric score
# (the program maps tier -> 0-100). It MUST NOT output any amount / composite.
NON_ECONOMIC_DIMENSIONS = ["workload", "stability", "growth", "match"]
NON_ECONOMIC_LABELS = {
    "workload": "工作强度",
    "stability": "稳定性",
    "growth": "发展空间",
    "match": "岗位匹配度",
}
TIER_TO_SCORE = {"high": 80, "medium": 55, "low": 30}


class F21Assessment(BaseModel):
    dimension: str  # workload | stability | growth | match
    tier: str  # high | medium | low (program-mapped, AI chooses tier not score)
    reason: str = ""  # why this tier (semantic explanation)
    evidence: str = ""  # what public info / user input supports it


class F21Output(BaseModel):
    assessments: list[F21Assessment] = Field(default_factory=list)

    @field_validator("assessments")
    @classmethod
    def _each_dimension(cls, v):
        for a in v:
            if a.dimension not in NON_ECONOMIC_DIMENSIONS:
                raise ValueError(f"unknown dimension: {a.dimension}")
            if a.tier not in TIER_TO_SCORE:
                raise ValueError(f"invalid tier: {a.tier}")
        return v


class F21Input(BaseModel):
    # Program-supplied, never invented by the model.
    company: str = ""
    job_title: str = ""
    city: str = ""
    # Public / user-provided context the AI may reason about (not scored numbers).
    public_signals: list[str] = Field(default_factory=list)  # e.g. 加班文化相关公开信息
    user_notes: str = ""  # user's own qualitative notes for this offer
    target_job_match: dict | None = None  # match_result payload from target_job (optional)


# ----------------------------- F24: decision analysis (Phase 6 Offer) -----------------------------
# The AI ONLY explains the comparison differences and conditional advice ("if you
# weight X more, A is better"). It MUST NOT output any score / ranking / amount /
# weight / composite -- those are the program's. It MUST NOT use absolute
# verdicts ("you should pick A"). Numbers are injected by the program; any number
# the model emits must match the injected data exactly (checked in validate_business).
class F24Recommendation(BaseModel):
    focus: str = ""  # 1-3 sentences: which dimensions drive the difference
    conditionals: list[str] = Field(default_factory=list)  # "若更看重薪资，B 更优" etc.
    caveats: list[str] = Field(default_factory=list)  # honest limitations / data gaps


class F24Output(BaseModel):
    recommendations: list[F24Recommendation] = Field(default_factory=list)


class F24Input(BaseModel):
    # Program-supplied deterministic data (the AI never recomputes these).
    offers: list[dict] = Field(default_factory=list)  # [{company,job_title,composite_score,dimension_scores,rank}]
    weights: dict = Field(default_factory=dict)
    weight_snapshot: dict = Field(default_factory=dict)
    city_costs: dict = Field(default_factory=dict)  # city -> monthly/yearly cost
    extra_context: str = ""
