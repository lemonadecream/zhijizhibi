"""Provider abstraction.

Business code only ever talks to ``BaseProvider.chat_json``. The concrete
provider (OpenAI-compatible or Mock for tests) is selected by configuration, so
adding a new protocol / local model later means adding a provider class only --
never touching business modules or prompts.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from app.ai.client import OpenAICompatibleClient, ProviderError
from app.config import settings


class BaseProvider(ABC):
    @abstractmethod
    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> dict:
        """Return a parsed JSON object from the model."""

    def chat_json_stream(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 2000):
        """Yield raw text deltas of the model output (streaming).

        Default for non-streaming providers: the complete output arrives as a
        single delta, so callers work unchanged.
        """
        content = self.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema={},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield json.dumps(content, ensure_ascii=False)


class OpenAIProvider(BaseProvider):
    def __init__(self):
        self._client = OpenAICompatibleClient(
            base_url=settings.AI_BASE_URL,
            api_key=settings.AI_API_KEY,
            model=settings.AI_MODEL,
            timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
        )

    def chat_json(self, *, system_prompt, user_prompt, output_schema, temperature=0.2, max_tokens=2000):
        content = self._client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            # The model returned non-JSON despite json_mode; treat as transient.
            raise ProviderError(f"model returned invalid JSON: {exc}", transient=True) from exc

    def chat_json_stream(self, *, system_prompt, user_prompt, temperature=0.2, max_tokens=2000):
        yield from self._client.chat_completion_stream(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )


class MockProvider(BaseProvider):
    """Deterministic provider for local testing -- returns schema-valid output.

    It does NOT call any network service. Used when ``AI_PROVIDER=mock``.
    """

    def chat_json(self, *, system_prompt, user_prompt, output_schema, temperature=0.2, max_tokens=2000):
        # Detect task by inspecting the requested schema's top-level properties.
        props = output_schema.get("properties", {})
        if "education" in props:
            return _mock_f1(user_prompt)
        if "ability_tags" in props:
            return _mock_f2(user_prompt)
        if "completion_ready" in props:
            return _mock_interview_step(user_prompt)
        if "duties" in props or "abilities" in props:
            return _mock_f9(user_prompt)
        if "judgements" in props:
            return _mock_f10(user_prompt)
        if "direction_hint" in props or "improvement_direction" in props:
            return _mock_f11(user_prompt)
        if "prep_items" in props:
            return _mock_f12(user_prompt)
        if "focus_items" in props:
            return _mock_f14(user_prompt)
        if "advices" in props:
            return _mock_f13(user_prompt)
        if "reason" in props:
            return _mock_f4(user_prompt)
        if "assessments" in props:
            return _mock_f21(user_prompt)
        if "recommendations" in props:
            return _mock_f24(user_prompt)
        # Generic safe fallback.
        return {}


def _snippet(text: str, n: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n]


def _mock_f1(user_prompt: str) -> dict:
    snippet = _snippet(user_prompt)
    return {
        "education": [
            {"school": "示例大学", "major": "计算机科学与技术", "degree": "本科",
             "start": "2020-09", "end": "2024-06"},
        ],
        "internships": [
            {"company": "示例科技有限公司", "role": "后端开发实习生",
             "start": "2023-06", "end": "2023-09", "duty": "参与后台服务开发与接口联调"},
        ],
        "projects": [
            {"name": "校园二手交易平台", "role": "后端负责人",
             "desc": "使用 Python 与 MySQL 实现交易与消息模块"},
        ],
        "skills": [
            {"name": "Python", "level": 3},
            {"name": "SQL", "level": 2},
            {"name": "FastAPI", "level": 2},
        ],
        "interests": ["后端开发", "数据分析"],
        "signals": [
            {"type": "preference", "text": "希望从事技术类岗位", "evidence": snippet or "希望从事技术类岗位"},
        ],
    }


def _mock_f2(user_prompt: str) -> dict:
    return {
        "positioning": "你更像一个喜欢把问题做成产品的分析型选手，正在寻找能落地、有成长空间的方向。",
        "tendencies": [
            {"axis": "探索性", "leaning": 0.75, "confidence": 0.7, "note": "愿意接触新领域"},
            {"axis": "稳定性", "leaning": 0.4, "confidence": 0.6, "note": "更看重成长"},
            {"axis": "自主性", "leaning": 0.7, "confidence": 0.6, "note": "喜欢主导推进"},
            {"axis": "协作性", "leaning": 0.6, "confidence": 0.5, "note": "能配合团队"},
        ],
        "motivations": ["把复杂问题拆清楚", "看到想法落地", "持续学习新东西"],
        "gaps": [
            {"item": "AI / 大模型项目经验", "why": "你提到对 AI 感兴趣但缺少可验证的落地项目", "evidence": "提到想做 AI 但暂未展开"},
            {"item": "大型产品完整闭环经验", "why": "现有项目规模偏小，缺少从 0 到 1 的完整经历", "evidence": "校园项目为主"},
        ],
        "career_goal": "希望从事与 AI 产品相关的方向",
        "ability_tags": [
            {"tag": "编程能力", "level": 3, "confidence": 0.8, "evidence": "后端开发实习生"},
            {"tag": "数据分析", "level": 2, "confidence": 0.7, "evidence": "校园二手交易平台"},
        ],
        "interest_tags": [
            {"tag": "后端开发", "evidence": "希望从事技术类岗位"},
        ],
        "strengths": [
            {"item": "具备后端开发实习经验", "evidence": "示例科技有限公司后端开发实习生"},
        ],
        "risks": [
            {"item": "缺乏大型生产系统经验", "evidence": "项目规模较小",
             "strategy": "参与开源项目或更大规模的系统实践"},
        ],
        "preference_infer": {"preferred_field": "技术类岗位"},
    }


# ----------------------------- Interview step mock state machine -----------------------------
# Deterministic, key-free demo: advances the six dimensions one per user turn,
# accumulates a progressive understanding, and flips completion_ready once all
# six are covered. Uses heuristic signal detection for corrections so the demo
# feels responsive without any LLM.
_DIM_SEQUENCE = ["D1", "D2", "D3", "D4", "D5", "D6"]
_DIM_LABEL = {
    "D1": "经历", "D2": "能力", "D3": "兴趣", "D4": "性格与工作方式",
    "D5": "价值观与动机", "D6": "求职意向",
}
_DIM_QUESTION = {
    "D1": "能再多讲讲这段经历里，你具体负责了什么吗？",
    "D2": "在这些事里，你觉得自己最拿手的是哪类能力？",
    "D3": "有没有哪个领域是你平时就特别喜欢琢磨的？",
    "D4": "你更喜欢一个人深度钻研，还是在团队里推动事情？",
    "D5": "选工作的时候，你更看重成长空间还是稳定性？",
    "D6": "你理想中的第一份工作，大概是什么样子？",
}
_DIM_TAG = {
    "D1": "有实际项目 / 实习经历",
    "D2": "具备落地执行能力",
    "D3": "有持续关注的兴趣方向",
    "D4": "有明确的工作方式偏好",
    "D5": "清楚自己看重的价值",
    "D6": "对求职方向有初步想法",
}


def _mock_interview_step(user_prompt: str) -> dict:
    # Heuristic: count how many user turns have happened so far.
    user_turns = user_prompt.count('"role": "user"')
    corrected = ("不是" in user_prompt) or ("更看重" in user_prompt) or ("其实" in user_prompt)

    covered_count = min(user_turns, len(_DIM_SEQUENCE))
    dimension_state = []
    for i, dim in enumerate(_DIM_SEQUENCE):
        covered = i < covered_count
        dimension_state.append({
            "dimension": dim,
            "covered": covered,
            "confidence": 0.6 if covered else 0.0,
            "note": _DIM_LABEL[dim] if covered else "",
        })

    tags = [_DIM_TAG[d] for d in _DIM_SEQUENCE[:covered_count]]
    if corrected:
        tags.append("已根据你的纠正更新理解")

    understanding = {
        "tags": tags,
        "sentences": [f"已了解你的{_DIM_LABEL[d]}" for d in _DIM_SEQUENCE[:covered_count]],
        "evidence": {t: "来自你的回答" for t in tags},
    }

    remaining = [d for d in _DIM_SEQUENCE if d not in _DIM_SEQUENCE[:covered_count]]
    wants_to_know = [_DIM_QUESTION[d] for d in remaining[:3]]

    completion_ready = covered_count >= len(_DIM_SEQUENCE)
    if completion_ready:
        response = "我已经大致了解你了。在开始给你推荐方向之前，想先确认一下下面这些描述。"
        questions = []
        summary_candidate = (
            "你有过实际的项目与实习经历，具备把事情落地的执行能力；平时对一个领域会持续投入，"
            "也有明确的工作方式偏好和价值判断。你正在寻找一份能成长、能落地、方向偏 AI 产品的工作。"
        )
    else:
        next_dim = _DIM_SEQUENCE[covered_count] if remaining else "D6"
        if corrected:
            response = "明白，我记下了你的纠正——这比我自己推断更重要。"
        else:
            response = "嗯，这个我记住了。我想再了解一点关于你的" + _DIM_LABEL[next_dim] + "。"
        questions = [_DIM_QUESTION[next_dim]]

    return {
        "response": response,
        "questions": questions,
        "understanding": understanding,
        "wants_to_know": wants_to_know,
        "dimension_state": dimension_state,
        "completion_ready": completion_ready,
        "summary_candidate": summary_candidate if completion_ready else "",
    }


def _mock_f4(user_prompt: str) -> dict:
    # Deterministic, key-free reason. The program has already supplied the match
    # basis in the prompt; we echo a stable, personal-sounding explanation so the
    # demo never needs a network call.
    return {
        "reason": (
            "这个方向和你已有的能力、兴趣比较对得上，而且工作方式也适合你目前的偏好，"
            "值得作为候选方向进一步了解。"
        ),
    }


# ----------------------------- F12 / F14 / F13 deterministic mocks (Phase 4) -----------------------------
# These mirror the schema keys so MockProvider routes to them without a network
# call. They return schema-valid, product-realistic outputs so the whole Prepare
# workspace demos offline (per Phase 4 纪律). They are KEY-FREE: they do not try
# to reproduce the live LLM; they return a stable, realistic PM-onboarding plan.
def _mock_f12(user_prompt: str) -> dict:
    """Deterministic preparation plan from Phase 3 gaps (offline-safe).

    The gateway embeds the gaps as a JSON object after a short natural-language
    prefix, so we extract the JSON (first '{' .. last '}') rather than parsing
    the whole prompt. We then emit one prep item PER input gap ability so the
    gateway's per-ability business validation passes for any gap set.
    """
    import json as _json

    gaps = []
    try:
        start = user_prompt.find("{")
        end = user_prompt.rfind("}")
        if start != -1 and end != -1 and end > start:
            blob = _json.loads(user_prompt[start:end + 1])
            gaps = blob.get("gaps", []) or []
    except Exception:
        gaps = []
    # Default demo gaps if the prompt had none parseable (offline-safe).
    if not gaps:
        gaps = [
            {"ability": "SQL", "priority": "medium",
             "improvement_direction": "通过数据项目补齐 SQL 熟练度"},
            {"ability": "行业经验", "priority": "low",
             "improvement_direction": "做行业调研输出竞品分析"},
        ]
    items = []
    for g in gaps:
        ability = g.get("ability", "该能力")
        if ability == "SQL":
            items.append({
                "ability": ability,
                "title": "补齐 SQL 数据分析能力",
                "reason": "岗位要求数据分析与 SQL，你目前仅有部分基础，达到熟练度可显著提升匹配。",
                "action_suggestion": "完成 1 个用 SQL 做用户行为分析的小项目，沉淀可展示的查询脚本与结论。",
            })
        elif ability == "行业经验":
            items.append({
                "ability": ability,
                "title": "补充目标行业认知与经验",
                "reason": "你缺少互联网产品行业的直接经验，这是岗位看重的加分项。",
                "action_suggestion": "做 2 周行业调研，输出一份竞品分析，并在项目中模拟真实行业场景。",
            })
        elif ability == "数据分析":
            items.append({
                "ability": ability,
                "title": "强化数据分析与复盘能力",
                "reason": "你具备部分基础，岗位要求用数据驱动迭代，需要更系统地补齐。",
                "action_suggestion": "在现有项目里补充一套指标看板与复盘模板，练习用数据讲结论。",
            })
        else:
            items.append({
                "ability": ability,
                "title": f"补齐「{ability}」能力",
                "reason": f"当前与岗位要求存在差距，属于 {g.get('priority','medium')} 优先级。",
                "action_suggestion": g.get("improvement_direction")
                or "建议通过贴近岗位的项目实践或系统学习建立该能力，并沉淀可验证成果。",
            })
    return {"prep_items": items}


# ---------------------------------------------------------------------------
# F13 / F14 mock 的"入参接地"层
#
# MockProvider 只服务本地开发与在线 Demo（AI_PROVIDER=mock），但它不能瞎编：
# 早先的 F13/F14 是为"产品经理"样例岗位写死的，于是运营方向的 Demo 会在
# 「求职准备」页看到"为什么想做产品经理"——与用户真实岗位无关，一眼假。
#
# 修法只有两步，不做任何自然语言生成：
#   1. 从 user_prompt 里读出真实入参（岗位、公司、能力、Gap、标签、经历标题）；
#   2. 用一张"岗位族 -> 第一问句式"的小表选措辞，其余槽位一律填真实入参。
# 岗位族判定不出来时，退化为不含任何岗位假设的通用句式。
#
# 真实 AI 路径（OpenAIProvider + prompts + gateway + schema）完全不受影响。
# ---------------------------------------------------------------------------
_SECTION_RE = re.compile(r"【([^】]+)】")

# 岗位族 -> 该族"第一问"的句式。只选句式，不含任何具体岗位名。
_ROLE_QUESTION = {
    "operations": "请讲一次你从真实用户反馈里发现机会点、并把它做成可落地方案的经历。",
    "product": "请介绍一次你主导需求从 0 到 1 落地的经历。",
    "data": "请讲一次你独立完成数据分析、并让结论真正影响决策的经历。",
    "marketing": "请讲一次你策划并落地一次推广活动的完整经历。",
    "hr": "请讲一次你处理过的最复杂的沟通或协作场景。",
    "sales": "请讲一次你从接触客户一路推进到成交的完整经历。",
    "tech": "请讲一次你负责的技术方案从设计到上线的经历。",
    "design": "请讲一次你从需求到交付完整走完的设计项目。",
}

# 判定顺序即优先级。注意「产品运营」「用户增长」必须先落到 operations，
# 不能被后面的「产品」抢走 —— 所以 operations 排在最前。
_ROLE_KEYWORDS = (
    ("operations", ("运营", "增长", "内容", "社群", "新媒体")),
    ("product", ("产品", "需求分析", "prd")),
    ("data", ("数据", "bi", "算法", "商业分析")),
    ("marketing", ("市场", "营销", "品牌", "公关", "投放", "推广")),
    ("hr", ("人力", "人事", "招聘", "培训", "组织发展", "hr")),
    ("sales", ("销售", "商务", "客户成功", "渠道", "bd")),
    ("tech", ("开发", "工程师", "研发", "后端", "前端", "测试", "运维", "架构")),
    ("design", ("设计", "视觉", "交互", "ux")),
)


def _prompt_sections(user_prompt: str) -> dict[str, str]:
    """把 prompt 按 ``【小节名】`` 切成 ``{小节名: 正文}``（正文截止到下一节）。"""
    text = user_prompt or ""
    sections: dict[str, str] = {}
    marks = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sections[m.group(1).strip()] = text[m.end():end].strip()
    return sections


def _prompt_job(user_prompt: str) -> tuple[str, str]:
    """读首行 ``目标岗位：<job_title> @ <company>``，读不到就返回空串。"""
    stripped = (user_prompt or "").strip()
    if not stripped:
        return "", ""
    first = stripped.splitlines()[0]
    body = first.split("：", 1)[-1] if "：" in first else ""
    job_title, _, company = body.partition("@")
    return job_title.strip(), company.strip()


def _loads_lenient(raw: str, default):
    """解析一段可能被说明文字"污染"的 JSON。

    prompt 的**最后一个**小节后面会跟一句收尾指令（如"请输出…JSON。"），所以直接
    ``json.loads`` 会失败。这里退一步：截取第一个 ``[`` / ``{`` 到最后一个 ``]`` / ``}``
    再试一次。两段都失败才返回 default。
    """
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = raw.find(opener), raw.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except (TypeError, ValueError):
                continue
    return default


def _section_json(sections: dict[str, str], key: str, default):
    """取一个小节并 json 解析；缺失或格式异常时返回 default。"""
    raw = sections.get(key)
    if not raw:
        return default
    value = _loads_lenient(raw, default)
    return value if isinstance(value, type(default)) else default


def _section_dicts(sections: dict[str, str], key: str) -> list[dict]:
    return [x for x in _section_json(sections, key, []) if isinstance(x, dict)]


def _section_strs(sections: dict[str, str], key: str) -> list[str]:
    return [str(x).strip() for x in _section_json(sections, key, []) if str(x).strip()]


def _role_family(*texts: str) -> str:
    """按顺序逐个文本判定岗位族：先看岗位名，再看职责 / 经历。都没有则 general。"""
    for text in texts:
        hay = (text or "").lower()
        if not hay:
            continue
        for family, keywords in _ROLE_KEYWORDS:
            if any(k in hay for k in keywords):
                return family
    return "general"


def _experience_titles(experiences: list[dict]) -> list[str]:
    """取经历标题，实习 / 项目优先（面试官最可能追问的），学历排最后。"""
    rank = {"internship": 0, "work": 0, "project": 1, "practice": 1}
    ordered = sorted(
        [e for e in experiences if e.get("title")],
        key=lambda e: rank.get(str(e.get("type") or ""), 2),
    )
    return [str(e["title"]).strip() for e in ordered if str(e["title"]).strip()]


def _ability_names(abilities: list[dict]) -> list[str]:
    return [str(a.get("name")).strip() for a in abilities if str(a.get("name") or "").strip()]


def _mock_f14(user_prompt: str) -> dict:
    """Deterministic interview focus, grounded in THIS prompt's job / abilities / gaps.

    只使用入参里真实存在的东西：岗位名、能力名、Gap、真实经历标题。
    岗位族只决定第一问的句式，不决定说的是哪个岗位。
    """
    sections = _prompt_sections(user_prompt)
    job_title, company = _prompt_job(user_prompt)
    abilities = _section_dicts(sections, "岗位能力模型")
    responsibilities = _section_strs(sections, "核心职责")
    gaps = _section_dicts(sections, "能力 Gap（partial/missing）")
    ability_tags = _section_strs(sections, "用户能力标签")
    exp_titles = _experience_titles(_section_dicts(sections, "用户真实经历（回答证据来源）"))

    job_label = job_title or "这个岗位"
    org_label = company or "这家公司"
    family = _role_family(job_title, " ".join(responsibilities), " ".join(exp_titles))

    # 优先问权重最高的 hard 能力，其次问能力标签里最强的一项。
    hard = [a for a in abilities if a.get("requirement_type") == "hard" or a.get("category") == "hard"]
    top_ability = (_ability_names(hard) or _ability_names(abilities) or ability_tags or ["岗位核心能力"])[0]
    top_exp = exp_titles[0] if exp_titles else ""

    # 第一问：岗位族提供句式，能力与经历来自入参。
    question_1 = _ROLE_QUESTION.get(family) or (
        f"请结合一段真实经历，讲清你是怎么把「{top_ability}」用在具体工作里的。"
    )
    related_exp_1 = top_exp or "（建议挑一段最贴近该能力的实习或项目经历）"

    items = [
        {
            "question": question_1,
            "reason": f"目标岗位「{job_label}」把「{top_ability}」列为核心要求，面试官通常会围绕它追问细节。",
            "related_requirement": top_ability,
            "related_experience": related_exp_1,
            "preparation_advice": "用 STAR 说清背景—动作—结果，重点讲你具体做了什么、带来了什么可衡量的变化。",
            "evidence_status": "sufficient" if top_exp else "insufficient",
        },
    ]

    # 第二问：问入参里真实存在的最大 Gap。
    if gaps:
        gap_ability = str(gaps[0].get("ability") or "").strip() or top_ability
        priority = str(gaps[0].get("priority") or "medium")
        items.append({
            "question": f"如果面试官问「你在{gap_ability}这块目前还差在哪里」，你打算怎么回答？",
            "reason": f"「{gap_ability}」是你当前与岗位要求差距较明显的一项"
                      f"（{'优先补齐' if priority == 'high' else '需要关注'}），大概率会被追问。",
            "related_requirement": gap_ability,
            "related_experience": "你已有的相关基础（需要补充更直接的证据）",
            "preparation_advice": "准备「已知短板 + 正在怎么补 + 已有进展」三段式回答：坦诚，但用行动说明你在缩小差距。",
            "evidence_status": "insufficient",
        })
    else:
        items.append({
            "question": f"请举一个例子，说明你如何保证「{top_ability}」的产出质量。",
            "reason": f"岗位对「{top_ability}」有要求，面试官会用具体例子验证你是否真的做过。",
            "related_requirement": top_ability,
            "related_experience": related_exp_1,
            "preparation_advice": "挑一段最能体现该项能力的经历，说清判断标准与取舍过程。",
            "evidence_status": "sufficient" if top_exp else "none",
        })

    # 第三问：动机题 —— 用真实岗位名与公司名，这是最容易被写错、也最显眼的一问。
    has_industry_gap = any("行业" in str(g.get("ability") or "") for g in gaps)
    items.append({
        "question": f"为什么想做{job_label}？为什么选择{org_label}？",
        "reason": f"考察求职动机与对「{org_label}」业务的理解，这是动机类问题的固定开场。",
        "related_requirement": "行业经验" if has_industry_gap else top_ability,
        "related_experience": (
            "（暂无直接行业经历，建议用一段行业调研替代）"
            if has_industry_gap
            else related_exp_1
        ),
        "preparation_advice": f"先把「你做过什么、因此看懂了什么」说清楚，再讲{org_label}哪一点"
                              "与你的判断吻合；避免只表达热情。",
        "evidence_status": "none" if has_industry_gap else ("sufficient" if exp_titles else "insufficient"),
    })

    return {"focus_items": items}


def _mock_f13(user_prompt: str) -> dict:
    """Deterministic resume advice, grounded in THIS prompt's strengths / gaps / experiences.

    与 F14 同一套路：建议指向的能力与经历必须来自入参，岗位只出现在「面向的岗位」语境里。
    """
    sections = _prompt_sections(user_prompt)
    job_title, _company = _prompt_job(user_prompt)
    strengths = _section_dicts(sections, "匹配优势")
    risks = _section_dicts(sections, "匹配风险")
    gaps = _section_dicts(sections, "能力 Gap")
    ability_tags = _section_strs(sections, "用户能力标签")
    exp_titles = _experience_titles(_section_dicts(sections, "用户真实经历"))

    job_label = job_title or "目标岗位"
    top_strength = next(
        (str(s.get("ability")).strip() for s in strengths if str(s.get("ability") or "").strip()),
        "",
    )
    anchor = top_strength or (ability_tags[0] if ability_tags else "与岗位最相关的核心能力")
    top_exp = exp_titles[0] if exp_titles else ""

    advices: list[dict] = [
        {
            "advice_type": "highlight",
            "content": (
                f"用「{top_exp}」这段经历承载「{anchor}」，并把结果写成可核验的表述"
                "（你做了什么、带来了什么变化），不要只写职责。"
                if top_exp
                else f"把最能体现「{anchor}」的那段经历放到简历靠前的位置，并补上可核验的结果表述。"
            ),
            "related_experience": top_exp,
            "related_gap": "",
            "severity": "high",
        },
    ]

    if gaps:
        gap_ability = str(gaps[0].get("ability") or "").strip() or anchor
        advices.append({
            "advice_type": "evidence_gap",
            "content": f"「{gap_ability}」目前缺少可直接核验的成果，建议补一个能体现该项能力的项目案例，"
                       "写清你的动作与结果。",
            "related_experience": "",
            "related_gap": gap_ability,
            "severity": "high" if str(gaps[0].get("priority") or "") == "high" else "medium",
        })
    else:
        advices.append({
            "advice_type": "evidence_gap",
            "content": "检查一遍简历里的成果描述是否都有对应证据（数字、产出物、他人评价），"
                       "没有证据的表述建议删掉或补齐。",
            "related_experience": "",
            "related_gap": "",
            "severity": "medium",
        })

    keyword_pool = [top_strength] + _ability_names(strengths) + ability_tags
    keyword_pool += [str(g.get("ability") or "").strip() for g in gaps]
    keywords = [k for k in dict.fromkeys(k.strip() for k in keyword_pool) if k][:4]
    advices.append({
        "advice_type": "keyword",
        "content": (
            f"围绕「{job_label}」这个目标，让简历里自然出现 "
            f"{'、'.join(f'「{k}」' for k in keywords)} 这类关键词，并各自对应到具体经历，避免只堆词。"
            if keywords
            else f"围绕「{job_label}」这个目标，把 JD 里的核心要求词自然地写进相关经历描述里，避免只堆词。"
        ),
        "related_experience": "",
        "related_gap": "",
        "severity": "low",
    })

    risk_ability = next(
        (str(r.get("ability")).strip() for r in risks if str(r.get("ability") or "").strip()),
        "",
    )
    advices.append({
        "advice_type": "weak_link",
        "content": (
            f"「{risk_ability}」与岗位的关联目前较弱，不要在简历里夸大；可以用一段行业或业务调研、"
            "竞品分析，体现你的学习力与诚意。"
            if risk_ability
            else f"删掉与「{job_label}」无关的关键词和经历，把篇幅留给最相关的几段。"
        ),
        "related_experience": "",
        "related_gap": risk_ability,
        "severity": "medium",
    })

    return {"advices": advices}


def get_provider() -> BaseProvider:
    if settings.AI_PROVIDER == "mock":
        return MockProvider()
    return OpenAIProvider()


# ----------------------------- F21 / F24 deterministic mocks (Phase 6 Offer) -----------------------------
def _mock_f21(user_prompt: str) -> dict:
    """Deterministic qualitative assessment for the four fixed dimensions.

    Offline-safe: returns a stable, plausible tier per dimension. The program
    maps tier -> 0-100; the AI never emits numbers here.
    """
    return {
        "assessments": [
            {"dimension": "workload", "tier": "medium",
             "reason": "公开信息显示该岗位存在一定节奏压力，但具体强度取决于团队。", "evidence": "行业通行节奏"},
            {"dimension": "stability", "tier": "high",
             "reason": "公司规模与岗位性质相对稳定，适合作为长期发展平台。", "evidence": "公司与岗位属性"},
            {"dimension": "growth", "tier": "high",
             "reason": "岗位涉及核心业务，成长空间较大。", "evidence": "岗位职责描述"},
            {"dimension": "match", "tier": "medium",
             "reason": "与你的能力画像基本匹配，部分能力仍需补齐。", "evidence": "用户备注"},
        ]
    }


def _mock_f24(user_prompt: str) -> dict:
    """Deterministic decision analysis that ONLY explains, never decides.

    Mirrors the schema keys so MockProvider routes to it. The numbers are
    injected by the program; we never invent or change them.
    """
    return {
        "recommendations": [
            {
                "focus": "差异主要来自经济收益与可支配收入：税后更高的 Offer 在「薪资优先」权重下更具优势。",
                "conditionals": [
                    "若你更看重稳定性而非收入，排序可能向稳定性更高的 Offer 倾斜。",
                    "若更看重发展空间，请上调「发展空间」权重后重新比较。",
                ],
                "caveats": ["分析基于你填写的信息，未涵盖未在系统中录入的隐性因素（如通勤、团队氛围）。"],
            }
        ]
    }


# ----------------------------- F9 / F10 / F11 deterministic mocks (Phase 3) -----------------------------
# These mirror the schema keys so the MockProvider branch detection routes to
# them without any network call. They return schema-valid, product-realistic
# outputs so the whole Target Job flow demos offline (per Phase 3 纪律).
def _mock_f9(user_prompt: str) -> dict:
    """Deterministic JD parse: a realistic product-manager JD when the input is
    substantial; minimal parse for tiny inputs."""
    low = (user_prompt or "").lower()
    # Detect a product-manager-ish JD by common keywords.
    is_pm = any(k in low for k in ["产品", "需求", "prd", "产品经理", "用户", "迭代"])
    if is_pm:
        return {
            "company": "示例科技有限公司",
            "title": "产品经理",
            "industry": "互联网 / 软件",
            "responsibilities": [
                "负责产品需求调研、PRD 撰写与评审",
                "推动设计、研发、测试跨团队落地",
                "通过数据复盘迭代产品功能",
                "跟踪行业与竞品动态",
            ],
            "abilities": [
                {"name": "需求分析", "category": "hard", "level": 4, "weight": 1.8, "requirement_type": "hard"},
                {"name": "沟通协调", "category": "hard", "level": 4, "weight": 1.5, "requirement_type": "hard"},
                {"name": "项目管理", "category": "hard", "level": 3, "weight": 1.3, "requirement_type": "hard"},
                {"name": "数据分析", "category": "soft", "level": 3, "weight": 1.2, "requirement_type": "soft"},
                {"name": "SQL", "category": "soft", "level": 2, "weight": 0.8, "requirement_type": "soft"},
                {"name": "行业经验", "category": "plus", "level": 3, "weight": 0.5, "requirement_type": "plus"},
            ],
            "requirements": {
                "education": "本科及以上",
                "experience_years": 2,
                "major": ["计算机", "管理", "相关方向"],
                "cert": [],
            },
            "other_requirements": ["具备良好的逻辑思维与表达能力"],
        }
    # Generic fallback parse: keep whatever the user hinted, plus a placeholder.
    return {
        "company": "",
        "title": "",
        "industry": "",
        "responsibilities": [],
        "abilities": [
            {"name": "相关能力（待确认）", "category": "hard", "level": 3, "weight": 1.0, "requirement_type": "hard"},
        ],
        "requirements": {"education": "", "experience_years": 0, "major": [], "cert": []},
        "other_requirements": [],
    }


def _mock_f10(user_prompt: str) -> dict:
    """Deterministic relation judgement for the product-manager ability model.

    Mirrors the realistic demo: 产品经理能力 -> covered, SQL -> partial,
    行业经验 -> missing. Uses the ability names present in the F9 mock model.
    """
    # Default coverage map for the demo PM JD; unknown abilities -> partial.
    coverage = {
        "需求分析": "covered",
        "沟通协调": "covered",
        "项目管理": "covered",
        "数据分析": "covered",
        "SQL": "partial",
        "行业经验": "missing",
    }
    # Recover the requested ability list from the prompt if possible; otherwise
    # use the demo set so the mock is stable for any input.
    abilities = list(coverage.keys())
    judgements = []
    for name in abilities:
        relation = coverage.get(name, "partial")
        if relation == "covered":
            reason = f"你的画像与经历中已经体现出「{name}」相关的能力与证据。"
            evidence = f"画像能力标签 / 经历中包含 {name} 相关项"
        elif relation == "partial":
            reason = f"你具备「{name}」的部分基础，但尚未达到岗位要求的熟练度。"
            evidence = f"存在相关基础，但缺少可验证的熟练度证据"
        else:
            reason = f"当前经历中缺少「{name}」的直接证据，判定为待补齐。"
            evidence = "未在画像 / 经历中发现相关项"
        judgements.append({"ability": name, "relation": relation, "reason": reason, "evidence": evidence})
    return {"judgements": judgements}


def _mock_f11(user_prompt: str) -> dict:
    """Deterministic gap explanation for a single ability (program pre-filled)."""
    # The program passes ability / required_level / current_evidence /
    # gap_degree / priority in the prompt; we echo a stable, supportive note.
    import json as _json

    ability = "该能力"
    try:
        # Best-effort extract the ability name from the JSON the gateway built.
        blob = _json.loads(user_prompt)
        ability = blob.get("ability", ability)
    except Exception:
        pass
    return {
        "why": f"当前证据显示你在「{ability}」上与岗位要求仍存在差距，需要重点补齐。",
        "evidence": "未在画像与经历中找到充分的直接证据",
        "improvement_direction": "建议通过贴近岗位的项目实践或系统学习建立该能力，并沉淀可验证的成果。",
    }
