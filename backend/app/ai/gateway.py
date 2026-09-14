"""AI Gateway: the single entry point for all AI calls in the system.

Flow per task:
    input -> validate input -> assemble context/prompt -> provider.chat_json
          -> parse JSON -> validate output (JSON Schema via Pydantic)
          -> business validation -> retry on failure -> fallback or raise

Design rules enforced here:
  * Business modules call ``gateway.run(task, input)`` -- they NEVER call the LLM directly.
  * The gateway does NOT write business data; it only returns a validated dict.
  * The gateway is decoupled from any model/vendor (selected via config).
  * On exhaustion it returns a degraded ``fallback`` result when available, or
    raises AIGatewayError -- never leaves the caller with a blank crash.
"""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.client import ProviderError
from app.ai.metrics import metrics
from app.ai.prompts import (
    F1_SYSTEM,
    F2_SYSTEM,
    F4_SYSTEM,
    F10_SYSTEM,
    F11_SYSTEM,
    F12_SYSTEM,
    F13_SYSTEM,
    F14_SYSTEM,
    F21_SYSTEM,
    F24_SYSTEM,
    F9_SYSTEM,
    INTERVIEW_SYSTEM,
    f10_user_prompt,
    f11_user_prompt,
    f12_user_prompt,
    f13_user_prompt,
    f14_user_prompt,
    f21_user_prompt,
    f24_user_prompt,
    f1_user_prompt,
    f2_user_prompt,
    f4_user_prompt,
    f9_user_prompt,
    interview_step_user_prompt,
)
from app.ai.provider import BaseProvider, get_provider
from app.ai.schemas import (
    F10Input,
    F10Output,
    F11Input,
    F11Output,
    F12Input,
    F12Output,
    F13Input,
    F13Output,
    F14Input,
    F14Output,
    F1Input,
    F1Output,
    F2Input,
    F2Output,
    F21Input,
    F21Output,
    F24Input,
    F24Output,
    F4Input,
    F4Output,
    F9Input,
    F9Output,
    InterviewStepInput,
    InterviewStepOutput,
)
from app.errors.exceptions import AIGatewayError, ValidationError_ as AppValidationError
from app.logging_config import logger


class AIResult:
    def __init__(self, *, status: str, data: dict, error: str | None = None, fallback_available: bool = False):
        self.status = status  # "ok" | "fallback"
        self.data = data
        self.error = error
        self.fallback_available = fallback_available


class RetryPolicy:
    def __init__(self, max_retries: int = 2, backoff: float = 0.5):
        self.max_retries = max_retries
        self.backoff = backoff


class AITask(ABC):
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    temperature: float = 0.2
    max_tokens: int = 2000
    retry: RetryPolicy = RetryPolicy()
    fallback_available: bool = True

    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def build_user_prompt(self, input_dict: dict) -> str: ...

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        """Extra checks beyond schema. Raise ValueError to trigger retry/fallback."""

    @abstractmethod
    def fallback(self, input_dict: dict, error: Exception | None) -> dict: ...


class F1ResumeParseTask(AITask):
    name = "f1_resume_parse"
    input_model = F1Input
    output_model = F1Output

    def system_prompt(self) -> str:
        return F1_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f1_user_prompt(input_dict["raw_text"])

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # F1Signal.evidence is required by the model already; ensure signals
        # reference something real (non-empty evidence).
        for s in output.signals:  # type: ignore[attr-defined]
            if not s.evidence or not s.evidence.strip():
                raise ValueError("signal evidence must be non-empty")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        return F1Output().model_dump()


class F2ProfileTask(AITask):
    name = "f2_profile"
    input_model = F2Input
    output_model = F2Output

    def system_prompt(self) -> str:
        return F2_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f2_user_prompt(
            input_dict.get("experiences", []),
            input_dict.get("career_goal"),
            input_dict.get("preference"),
            input_dict.get("interview_context"),
        )

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        return F2Output().model_dump()


class InterviewStepTask(AITask):
    name = "interview_step"
    input_model = InterviewStepInput
    output_model = InterviewStepOutput
    temperature = 0.6  # warmer, more conversational than F1/F2
    max_tokens = 1200

    def system_prompt(self) -> str:
        return INTERVIEW_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return interview_step_user_prompt(
            entry_method=input_dict.get("entry_method", "scratch"),
            histories=input_dict.get("history", []),
            understanding=input_dict.get("understanding", {}),
            dimension_state=input_dict.get("dimension_state", []),
            wants_to_know=input_dict.get("wants_to_know", []),
            latest_message=input_dict.get("latest_message", ""),
            experiences=input_dict.get("experiences", []),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # Guardrails: never let the model dump a questionnaire.
        if len(output.questions) > 2:  # type: ignore[attr-defined]
            raise ValueError("interview_step must ask at most 2 questions")
        if len(output.response or "") > 600:
            raise ValueError("interview_step response too long")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        # Degraded but safe: keep the conversation moving with a gentle prompt.
        out = InterviewStepOutput()
        out.response = "我刚才有点没听清，能再展开说说吗？"
        out.questions = ["你刚才提到的经历里，最让你有成就感的是哪一件？"]
        return out.model_dump()


class F4DirectionReasonTask(AITask):
    """Phase 2 Explore: the ONLY AI-authored field in recommendations.

    The program computes the score, ranking and match basis. The AI merely
    writes a warm, personal "why this direction fits your profile" paragraph.
    On failure it degrades to a program-built template reason (see fallback),
    so Explore works fully offline.
    """

    name = "f4_direction_reason"
    input_model = F4Input
    output_model = F4Output
    temperature = 0.4
    max_tokens = 400
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F4_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f4_user_prompt(
            direction_name=input_dict.get("direction_name", ""),
            direction_summary=input_dict.get("direction_summary", ""),
            direction_core_abilities=input_dict.get("direction_core_abilities", []),
            direction_work_styles=input_dict.get("direction_work_styles", []),
            user_positioning=input_dict.get("user_positioning", ""),
            user_ability_tags=input_dict.get("user_ability_tags", []),
            user_interest_tags=input_dict.get("user_interest_tags", []),
            user_strengths=input_dict.get("user_strengths", []),
            match_basis=input_dict.get("match_basis", []),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        if not (output.reason or "").strip():  # type: ignore[attr-defined]
            raise ValueError("f4 reason must be non-empty")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        # Offline-safe reason: echo the program's deterministic match basis in
        # natural language so the card still has a human-readable explanation.
        basis = input_dict.get("match_basis") or []
        if basis:
            reason = "根据你的画像，" + "；".join(basis[:2]) + "。"
        else:
            reason = "这个方向与你的画像有一定契合度，建议进一步了解。"
        return {"reason": reason}


class F9JdParseTask(AITask):
    """Phase 3 Target Job: the ONLY AI-authored field in JD creation.

    The program validates the parsed ability model (category enum, weight
    bounds, non-empty requirements) and owns all downstream scoring. The AI
    merely extracts structure from free text. On failure it degrades to a
    program-built, keyword-light fallback so JD creation works fully offline.
    """

    name = "f9_jd_parse"
    input_model = F9Input
    output_model = F9Output
    temperature = 0.2
    max_tokens = 2200
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F9_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f9_user_prompt(
            raw_jd=input_dict.get("raw_jd", ""),
            job_title=input_dict.get("job_title", ""),
            company=input_dict.get("company", ""),
            city=input_dict.get("city", ""),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # Require at least a title or some abilities so the parse is useful.
        if not (output.title or output.abilities):
            raise ValueError("f9 parse must yield a title or at least one ability")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        # Offline-safe parse: echo the user's auxiliary hints + a minimal
        # ability placeholder so the user can still edit and confirm a JD.
        raw = (input_dict.get("raw_jd") or "").strip()
        abilities = [{"name": "相关能力（待确认）", "category": "hard", "level": 3,
                      "weight": 1.0, "requirement_type": "hard"}] if raw else []
        return {
            "company": input_dict.get("company", "") or "",
            "title": input_dict.get("job_title", "") or "",
            "industry": "",
            "responsibilities": [],
            "abilities": abilities,
            "requirements": {"education": "", "experience_years": 0, "major": [], "cert": []},
            "other_requirements": [],
        }


class F10MatchJudgeTask(AITask):
    """Phase 3 Target Job: AI judges ONLY the semantic relation per ability.

    The AI emits ``covered`` / ``partial`` / ``missing`` + reason + evidence for
    each required ability. It MUST NOT output any score. The program maps
    relations to coverage values and computes the final match score, dimensions,
    strengths and risks. On failure it degrades to a program keyword match.
    """

    name = "f10_match_judge"
    input_model = F10Input
    output_model = F10Output
    temperature = 0.2
    max_tokens = 2500
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F10_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f10_user_prompt(
            profile_ability_tags=input_dict.get("profile_ability_tags", []),
            profile_strengths=input_dict.get("profile_strengths", []),
            experiences=input_dict.get("experiences", []),
            ability_model=input_dict.get("ability_model", {}),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # Every ability in the model must have a judgement with a valid relation.
        abilities = (input_dict.get("ability_model", {}) or {}).get("abilities", []) or []
        judged = {j.ability for j in output.judgements}  # type: ignore[attr-defined]
        for ab in abilities:
            if ab.get("name") not in judged:
                raise ValueError(f"missing judgement for ability: {ab.get('name')}")
        for j in output.judgements:  # type: ignore[attr-defined]
            if j.relation not in ("covered", "partial", "missing"):
                raise ValueError(f"invalid relation: {j.relation}")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        # Offline-safe: keyword match between ability names and the user's
        # ability tags / strengths / experience titles.
        abilities = (input_dict.get("ability_model", {}) or {}).get("abilities", []) or []
        tags = set(input_dict.get("profile_ability_tags", []) or [])
        strengths = set(input_dict.get("profile_strengths", []) or [])
        exp_text = " ".join(
            f"{e.get('title','')} {e.get('detail','')}" for e in (input_dict.get("experiences", []) or [])
        )
        judgements = []
        for ab in abilities:
            name = ab.get("name", "")
            hay = " ".join([name] + list(tags) + list(strengths))
            if name and (name in hay or name in exp_text):
                relation = "covered"
            elif name and any(name in t or t in name for t in (tags | strengths)):
                relation = "partial"
            else:
                relation = "missing"
            judgements.append({
                "ability": name,
                "relation": relation,
                "reason": "（AI 暂不可用，已用关键词匹配做近似判断，精确度较低）",
                "evidence": "基于画像能力标签与经历关键词匹配",
            })
        return {"judgements": judgements}


class F11GapExplainTask(AITask):
    """Phase 3 Target Job: AI explains a gap the program already identified.

    The program computes ``gap_degree`` (0..1) and ``priority``. The AI only
    writes the human explanation (why / evidence / improvement_direction). On
    failure it degrades to a deterministic template so gaps still render.
    """

    name = "f11_gap_explain"
    input_model = F11Input
    output_model = F11Output
    temperature = 0.3
    max_tokens = 600
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F11_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f11_user_prompt(
            ability=input_dict.get("ability", ""),
            required_level=input_dict.get("required_level"),
            current_evidence=input_dict.get("current_evidence", []),
            gap_degree=input_dict.get("gap_degree", 0.0),
            priority=input_dict.get("priority", "medium"),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        if not (output.why or "").strip():  # type: ignore[attr-defined]
            raise ValueError("f11 why must be non-empty")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        ability = input_dict.get("ability", "该能力")
        priority = input_dict.get("priority", "medium")
        return {
            "why": f"当前证据显示你在「{ability}」上与岗位要求仍存在差距，属于{priority}优先级，需要重点补齐。",
            "evidence": "；".join(input_dict.get("current_evidence", []) or []) or "暂无明确证据材料",
            "improvement_direction": "建议结合岗位要求，通过项目实践或系统学习逐步建立该能力，并在经历中沉淀可验证的证据。",
        }


class F12PreparationPlanTask(AITask):
    """Phase 4 Preparation: converts Phase 3 gaps into actionable prep advice.

    The program owns gap selection, priority and completion. The AI ONLY writes
    the human explanation: a task title + why-prepare + how-to per gap. It must
    NOT output any priority / score / number. On failure it degrades to a
    deterministic per-gap template so the plan still renders offline.
    """

    name = "f12_preparation_plan"
    input_model = F12Input
    output_model = F12Output
    temperature = 0.3
    max_tokens = 2500
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F12_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f12_user_prompt(
            job_title=input_dict.get("job_title", ""),
            company=input_dict.get("company", ""),
            gaps=input_dict.get("gaps", []),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # Every gap in the input must get a prep item keyed by the same ability.
        gap_abilities = {g.get("ability") for g in input_dict.get("gaps", []) if g.get("ability")}
        out_abilities = {it.ability for it in output.prep_items}  # type: ignore[attr-defined]
        for ab in gap_abilities:
            if ab not in out_abilities:
                raise ValueError(f"missing prep item for ability: {ab}")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        items = []
        for g in input_dict.get("gaps", []):
            ability = g.get("ability", "该能力")
            items.append({
                "ability": ability,
                "title": f"补齐「{ability}」能力",
                "reason": f"当前与岗位要求存在差距，属于 {g.get('priority', 'medium')} 优先级，建议重点准备。",
                "action_suggestion": g.get("improvement_direction")
                or "建议通过贴近岗位的项目实践或系统学习建立该能力，并沉淀可验证的成果。",
            })
        return {"prep_items": items}


class F14InterviewFocusTask(AITask):
    """Phase 4 Interview Focus: predicts likely questions, grounded in experience.

    The AI proposes questions + prep advice, each bound to a JD requirement and a
    real user experience where possible. It must NOT output any score / number.
    On failure it degrades to a small deterministic, experience-grounded set.
    """

    name = "f14_interview_focus"
    input_model = F14Input
    output_model = F14Output
    temperature = 0.3
    max_tokens = 2200
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F14_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f14_user_prompt(
            job_title=input_dict.get("job_title", ""),
            company=input_dict.get("company", ""),
            abilities=input_dict.get("abilities", []),
            responsibilities=input_dict.get("responsibilities", []),
            gaps=input_dict.get("gaps", []),
            profile_positioning=input_dict.get("profile_positioning", ""),
            ability_tags=input_dict.get("ability_tags", []),
            strengths=input_dict.get("strengths", []),
            experiences=input_dict.get("experiences", []),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        if not output.focus_items:  # type: ignore[attr-defined]
            raise ValueError("f14 must produce at least one focus item")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        gaps = input_dict.get("gaps", []) or []
        exps = input_dict.get("experiences", []) or []
        first_exp = ""
        if exps:
            e = exps[0]
            first_exp = f"{e.get('title','')} {e.get('detail','')}".strip()
        items = []
        for g in gaps[:3]:
            ability = g.get("ability", "该能力")
            items.append({
                "question": f"请结合经历，说明你在「{ability}」上的实践与成果。",
                "reason": f"该岗位明确要求「{ability}」，且这是你的能力 Gap 之一。",
                "related_requirement": ability,
                "related_experience": first_exp or "（请在你的经历中寻找对应项）",
                "preparation_advice": "用 STAR 结构（背景-任务-动作-结果）准备一段 2 分钟回答，并准备量化成果。",
                "evidence_status": "insufficient",
            })
        if not items:
            items.append({
                "question": "请介绍一下你最自豪的一段经历，以及它体现了你的哪些能力。",
                "reason": "通用开场问题，用于考察表达与自我认知。",
                "related_requirement": "",
                "related_experience": first_exp or "",
                "preparation_advice": "准备一段简洁、有结构的自我介绍。",
                "evidence_status": "sufficient" if first_exp else "none",
            })
        return {"focus_items": items}


class F13ResumeAdviceTask(AITask):
    """Phase 4 Resume Advice (P1, lightweight): targeted resume tweaks.

    The AI gives highlight / evidence_gap / keyword / weak_link suggestions for
    THIS target job. It must NOT rewrite the resume or output any number. On
    failure it degrades to a small deterministic hint set.
    """

    name = "f13_resume_advice"
    input_model = F13Input
    output_model = F13Output
    temperature = 0.2
    max_tokens = 1600
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F13_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f13_user_prompt(
            job_title=input_dict.get("job_title", ""),
            company=input_dict.get("company", ""),
            strengths=input_dict.get("strengths", []),
            risks=input_dict.get("risks", []),
            gaps=input_dict.get("gaps", []),
            ability_tags=input_dict.get("ability_tags", []),
            experiences=input_dict.get("experiences", []),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        if not output.advices:  # type: ignore[attr-defined]
            raise ValueError("f13 must produce at least one advice")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        gaps = input_dict.get("gaps", []) or []
        tags = input_dict.get("ability_tags", []) or []
        advices = []
        for g in gaps[:3]:
            ability = g.get("ability", "该能力")
            advices.append({
                "advice_type": "evidence_gap",
                "content": f"「{ability}」证据不足，建议在简历中用一段项目或实习经历体现相关成果。",
                "related_experience": "",
                "related_gap": ability,
                "severity": g.get("priority", "medium"),
            })
        if tags:
            advices.append({
                "advice_type": "keyword",
                "content": "建议在简历中自然体现与 JD 相关的能力关键词：" + "、".join(tags[:5]),
                "related_experience": "",
                "related_gap": "",
                "severity": "low",
            })
        if not advices:
            advices.append({
                "advice_type": "highlight",
                "content": "建议突出与目标岗位最相关的 1-2 段经历，量化你的贡献与成果。",
                "related_experience": "",
                "related_gap": "",
                "severity": "medium",
            })
        return {"advices": advices}


class F21DimensionTask(AITask):
    """Phase 6 Offer: AI assesses the FOUR fixed non-economic dimensions.

    The AI ONLY picks a tier (high/medium/low) + reason + evidence per dimension.
    It MUST NOT output a numeric score -- the program maps tier -> 0-100. It MUST
    NOT output any amount / composite / ranking. On failure it degrades to a
    deterministic "medium" baseline so the offer card still renders offline.
    """

    name = "f21_dimension_assess"
    input_model = F21Input
    output_model = F21Output
    temperature = 0.3
    max_tokens = 1200
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F21_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f21_user_prompt(
            company=input_dict.get("company", ""),
            job_title=input_dict.get("job_title", ""),
            city=input_dict.get("city", ""),
            public_signals=input_dict.get("public_signals", []),
            user_notes=input_dict.get("user_notes", ""),
            target_job_match=input_dict.get("target_job_match"),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        dims = {a.dimension for a in output.assessments}  # type: ignore[attr-defined]
        for d in ("workload", "stability", "growth", "match"):
            if d not in dims:
                raise ValueError(f"f21 missing assessment for dimension: {d}")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        return {
            "assessments": [
                {"dimension": d, "tier": "medium", "reason": "AI 暂不可用，已用中性档位兜底，建议自行评估。", "evidence": ""}
                for d in ("workload", "stability", "growth", "match")
            ]
        }


class F24DecisionAnalysisTask(AITask):
    """Phase 6 Offer: AI explains the computed comparison, never recomputes it.

    The program injects the fully-computed scores / ranks / costs. The AI only
    writes focused, conditional, non-absolute analysis. It MUST NOT output any
    number / rank / amount / weight; if it does, validate_business rejects it.
    On failure it degrades to a deterministic template so the panel still renders.
    """

    name = "f24_decision_analysis"
    input_model = F24Input
    output_model = F24Output
    temperature = 0.4
    max_tokens = 900
    retry = RetryPolicy(max_retries=1, backoff=0.4)

    def system_prompt(self) -> str:
        return F24_SYSTEM

    def build_user_prompt(self, input_dict: dict) -> str:
        return f24_user_prompt(
            offers=input_dict.get("offers", []),
            weights=input_dict.get("weights", {}),
            weight_snapshot=input_dict.get("weight_snapshot", {}),
            city_costs=input_dict.get("city_costs", {}),
            extra_context=input_dict.get("extra_context", ""),
        )

    def validate_business(self, output: BaseModel, input_dict: dict) -> None:
        # Hard guard: the model must not leak any number that conflicts with the
        # program-injected data. We strip and scan the free-text fields.
        injected = input_dict.get("offers", []) or []
        injected_numbers = set()
        for o in injected:
            for key in ("composite_score", "rank"):
                if o.get(key) is not None:
                    injected_numbers.add(str(o[key]))
        # Build the union of all numeric tokens across free-text outputs.
        blob = " ".join(
            [output.recommendations[0].focus if output.recommendations else ""]  # type: ignore[attr-defined]
            + [c for r in output.recommendations for c in r.conditionals]  # type: ignore[attr-defined]
            + [c for r in output.recommendations for c in r.caveats]  # type: ignore[attr-defined]
        )
        # Reject obvious absolute verdicts (the model must not decide for the user).
        absolute_patterns = ["你应该选", "建议选择", "最优", "最合适", "明显更好", "强烈推荐", "必须选"]
        for pat in absolute_patterns:
            if pat in blob:
                raise ValueError(f"f24 must not output absolute verdicts: {pat}")
        # Reject emitted numbers that are NOT among the program-injected ones
        # (e.g. the model inventing a score). Allow short percentages is risky;
        # we only permit the exact injected numbers to appear.
        import re
        found = set(re.findall(r"-?\d+(?:\.\d+)?", blob))
        for num in found:
            # allow harmless counters; reject standalone monetary/score-like numbers
            if num not in injected_numbers and (("." in num) or int(num.replace(".", "")) >= 10):
                raise ValueError(f"f24 emitted an unsupported number: {num}")

    def fallback(self, input_dict: dict, error: Exception | None) -> dict:
        offers = input_dict.get("offers", []) or []
        if offers:
            top = max(offers, key=lambda o: o.get("composite_score", 0))
            focus = (
                f"本次比较中，「{top.get('company','')} {top.get('job_title','')}」综合得分靠前，"
                "主要来自其在经济收益与可支配收入的相对优势。"
            )
        else:
            focus = "暂无足够数据，建议先补充 Offer 的经济与非经济信息。"
        return {
            "recommendations": [
                {
                    "focus": focus,
                    "conditionals": [
                        "若你更看重稳定性而非收入，排序可能有所变化，请以权重设置中的偏好为准。",
                        "若更看重发展空间，请适当上调「发展空间」权重后重新比较。",
                    ],
                    "caveats": ["分析基于你填写的信息，未考虑未在系统中录入的隐性因素。"],
                }
            ]
        }


class AIGateway:
    def __init__(self, provider: BaseProvider):
        self.provider = provider
        self.tasks: dict[str, AITask] = {}
        for task in (F1ResumeParseTask(), F2ProfileTask(), InterviewStepTask(),
                     F4DirectionReasonTask(), F9JdParseTask(),
                     F10MatchJudgeTask(), F11GapExplainTask(),
                     F12PreparationPlanTask(), F14InterviewFocusTask(),
                     F13ResumeAdviceTask(), F21DimensionTask(),
                     F24DecisionAnalysisTask()):
            self.tasks[task.name] = task

    def run(self, name: str, input_dict: dict) -> AIResult:
        task = self.tasks.get(name)
        if task is None:
            raise AIGatewayError(f"unknown AI task: {name}", task=name)

        try:
            inp = task.input_model(**input_dict)
        except ValidationError as exc:
            raise AppValidationError(f"AI task input invalid: {exc}") from exc

        output_schema = task.output_model.model_json_schema()
        system = task.system_prompt()
        user = task.build_user_prompt(inp.model_dump())

        started = time.monotonic()
        attempts = 0
        last_error: Exception | None = None
        for attempt in range(task.retry.max_retries + 1):
            attempts = attempt + 1
            try:
                raw = self.provider.chat_json(
                    system_prompt=system,
                    user_prompt=user,
                    output_schema=output_schema,
                    temperature=task.temperature,
                    max_tokens=task.max_tokens,
                )
                out = task.output_model.model_validate(raw)  # JSON-Schema validation
                task.validate_business(out, inp.model_dump())  # business rules
                self._record(name, "ok", started, attempts)
                return AIResult(status="ok", data=out.model_dump())
            except (ProviderError, ValidationError) as exc:
                last_error = exc
                logger.warning("AI task %s attempt %d failed: %s", name, attempt + 1, exc)
                if attempt < task.retry.max_retries:
                    time.sleep(task.retry.backoff)
                    continue

        if task.fallback_available:
            try:
                fb = task.fallback(inp.model_dump(), last_error)
            except Exception as exc:  # pragma: no cover - fallback is trivial
                self._record(name, "error", started, attempts, str(exc))
                raise AIGatewayError(f"fallback failed: {exc}", task=name) from exc
            self._record(name, "fallback", started, attempts, str(last_error))
            return AIResult(
                status="fallback", data=fb, error=str(last_error), fallback_available=True
            )
        self._record(name, "error", started, attempts, str(last_error))
        raise AIGatewayError(
            f"AI task {name} failed after {task.retry.max_retries + 1} attempts: {last_error}",
            task=name,
        )

    @staticmethod
    def _record(task: str, status: str, started: float, attempts: int, error: str = "") -> None:
        """Structured usage log + in-process metrics (P0-AI 可观测性).

        一行日志回答：哪个任务、成功还是降级、试了几次、花了多久。
        """
        latency_ms = int((time.monotonic() - started) * 1000)
        metrics.record(task, status, latency_ms, error)
        logger.info(
            "AI_CALL task=%s status=%s attempts=%d latency_ms=%d%s",
            task,
            status,
            attempts,
            latency_ms,
            f" error={error[:120]}" if error else "",
        )

    def run_interview_stream(self, input_dict: dict):
        """interview_step 的流式变体（SSE 用）。

        依次产出：
          ("delta", raw_delta) —— 模型原始输出的增量（服务层从中提取 response 字段）
          ("final", AIResult)  —— 完整结果（已过 schema + 业务校验；失败走 fallback）

        流式无法中途重试（会重复输出），因此单次尝试：失败直接走与 run() 相同
        语义的 fallback，保证对话不中断。
        """
        task = self.tasks["interview_step"]
        try:
            inp = task.input_model(**input_dict)
        except ValidationError as exc:
            raise AppValidationError(f"AI task input invalid: {exc}") from exc

        system = task.system_prompt()
        user = task.build_user_prompt(inp.model_dump())
        started = time.monotonic()
        chunks: list[str] = []
        try:
            for delta in self.provider.chat_json_stream(
                system_prompt=system,
                user_prompt=user,
                temperature=task.temperature,
                max_tokens=task.max_tokens,
            ):
                chunks.append(delta)
                yield ("delta", delta)
        except ProviderError as exc:
            fb = task.fallback(inp.model_dump(), exc)
            self._record("interview_step", "fallback", started, 1, str(exc))
            yield ("final", AIResult(status="fallback", data=fb, error=str(exc), fallback_available=True))
            return

        raw = "".join(chunks)
        try:
            out = task.output_model.model_validate_json(raw)
            task.validate_business(out, inp.model_dump())
            self._record("interview_step", "ok", started, 1)
            yield ("final", AIResult(status="ok", data=out.model_dump()))
        except (ValidationError, ValueError) as exc:
            fb = task.fallback(inp.model_dump(), exc)
            self._record("interview_step", "fallback", started, 1, str(exc))
            yield ("final", AIResult(status="fallback", data=fb, error=str(exc), fallback_available=True))


_GATEWAY: AIGateway | None = None


def partial_response_text(raw: str) -> str:
    """从流式累积的原始 JSON 中增量提取 response 字段的已生成文本。

    前提：interview_step 的输出 JSON 中 "response" 是第一个字段（prompt 已约定）。
    提取不到（字段还没开始）返回空串；转义字符做最小还原；遇到未转义的收尾引号即停。
    """
    m = re.search(r'"\s*response\s*"\s*:\s*"', raw)
    if not m:
        return ""
    rest = raw[m.end():]
    out: list[str] = []
    i = 0
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
    while i < len(rest):
        ch = rest[i]
        if ch == "\\" and i + 1 < len(rest):
            out.append(simple.get(rest[i + 1], rest[i + 1]))
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def get_gateway() -> AIGateway:
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = AIGateway(get_provider())
    return _GATEWAY
