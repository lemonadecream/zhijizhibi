"""F13 / F14 mock 文案必须"贴着入参"生成（回归测试）。

背景
----
MockProvider 的 F13（简历建议）/ F14（面试重点）此前是按"产品经理"样例岗位**写死**
的：不读 JD、不读用户经历。于是运营方向的 Demo 会在「求职准备」页看到
「为什么想做产品经理」——与用户真实岗位无关，一眼就是假的。

这组测试锁住三件事：

1. **不引入入参里没有的岗位假设**：非产品岗的文案里不允许出现产品岗专属词。
2. **只使用入参里真实存在的能力 / Gap / 经历**：``related_requirement``、
   ``related_gap`` 必须来自 prompt 里的能力集合或 Gap 集合；锚定的经历标题
   必须来自 prompt 里的真实经历。
3. **仍然遵守"AI 零数字"纪律**：不输出分数、百分比、薪资、金额。

第 2 条同时是"prompt 格式漂移"的探测器：一旦 ``prompts.py`` 里的小节标题被改名，
解析会退化为通用文案，``related_requirement`` 不再是入参里的能力名，测试立刻失败。

范围说明：F9（JD 解析）里也有同类硬编码（``_mock_f9`` 的 ``is_pm`` 分支会把含"用户"
的 JD 也判成产品经理），但那是本次改动范围之外，见文件末尾注释。
"""
from __future__ import annotations

import json

import pytest

from app.ai.prompts import f13_user_prompt, f14_user_prompt
from app.ai.provider import MockProvider, _mock_f13, _mock_f14, _role_family
from app.ai.schemas import F13Output, F14Output

# 只有产品岗才允许出现的词。非产品岗文案里出现任意一个即为"岗位错配"。
PRODUCT_ONLY_WORDS = ("产品经理", "PRD", "产品思维", "需求评审", "原型图")

ABILITY_NAMES = ("需求分析", "数据分析", "沟通协调", "行业经验")
GAP_NAMES = ("行业经验", "SQL")
EXP_TITLES = ("潮汐电商 内容运营实习生", "校园社团招新增长实验")

ABILITY_LIST = [
    {"name": "需求分析", "category": "hard", "requirement_type": "hard", "level": 4, "weight": 1.6},
    {"name": "数据分析", "category": "hard", "requirement_type": "hard", "level": 4, "weight": 1.7},
    {"name": "沟通协调", "category": "hard", "requirement_type": "hard", "level": 4, "weight": 1.3},
    {"name": "行业经验", "category": "hard", "requirement_type": "hard", "level": 3, "weight": 1.0},
]
RESPONSIBILITIES = ["设计并落地内容平台的拉新与促活实验", "分析用户行为数据，定位增长机会点"]
GAP_LIST = [
    {"ability": "行业经验", "priority": "high", "why": "缺少直接证据", "gap_degree": 1.0},
    {"ability": "SQL", "priority": "medium", "why": "缺少直接证据", "gap_degree": 0.5},
]
ABILITY_TAGS = ["用户调研", "内容策划", "社群运营"]
STRENGTH_LIST = [
    {"ability": "需求分析", "category": "hard", "evidence": "经历中包含相关内容"},
    {"ability": "数据分析", "category": "hard", "evidence": "经历中包含相关内容"},
]
RISK_LIST = [{"ability": "行业经验", "relation": "missing", "category": "hard", "evidence": "未发现相关项"}]
EXPERIENCE_LIST = [
    {"type": "education", "title": "江城大学 市场营销", "detail": "本科"},
    {"type": "internship", "title": "潮汐电商 内容运营实习生", "detail": ""},
    {"type": "project", "title": "校园社团招新增长实验", "detail": "转化率从 12% 提升到 27%"},
]


def _f14_prompt(job_title: str = "用户增长", company: str = "麦浪文化", **overrides) -> str:
    """用真实的 prompt 构造函数造入参，保证被测的正是线上同一条 prompt 格式。"""
    kwargs = {
        "job_title": job_title,
        "company": company,
        "abilities": ABILITY_LIST,
        "responsibilities": RESPONSIBILITIES,
        "gaps": GAP_LIST,
        "profile_positioning": "擅长用内容与社群触达用户的运营型选手。",
        "ability_tags": ABILITY_TAGS,
        "strengths": ["能把用户反馈转化为可执行的内容策略"],
        "experiences": EXPERIENCE_LIST,
    }
    kwargs.update(overrides)
    return f14_user_prompt(**kwargs)


def _f13_prompt(job_title: str = "用户增长", company: str = "麦浪文化", **overrides) -> str:
    kwargs = {
        "job_title": job_title,
        "company": company,
        "strengths": STRENGTH_LIST,
        "risks": RISK_LIST,
        "gaps": GAP_LIST,
        "ability_tags": ABILITY_TAGS,
        "experiences": EXPERIENCE_LIST,
    }
    kwargs.update(overrides)
    return f13_user_prompt(**kwargs)


def _blob(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


# ===========================================================================
# 岗位族判定
# ===========================================================================
@pytest.mark.parametrize("job_title,expected", [
    ("用户增长", "operations"),
    ("产品运营", "operations"),      # 含"产品"但必须优先判为运营
    ("内容运营", "operations"),
    ("新媒体运营", "operations"),
    ("产品经理", "product"),
    ("数据产品经理", "product"),
    ("数据分析师", "data"),
    ("市场专员", "marketing"),
    ("品牌公关", "marketing"),
    ("人力资源专员", "hr"),
    ("招聘专员", "hr"),
    ("销售经理", "sales"),
    ("后端开发工程师", "tech"),
    ("测试工程师", "tech"),
    ("视觉设计师", "design"),
    ("星际探索员", "general"),      # 认不出来必须退化为 general，不能瞎猜
    ("", "general"),
])
def test_role_family_detection(job_title, expected):
    assert _role_family(job_title) == expected


# ===========================================================================
# F14 面试重点
# ===========================================================================
def test_f14_grounded_on_prompt_inputs():
    """岗位名、能力名、Gap、经历标题都必须能回溯到入参。"""
    items = _mock_f14(_f14_prompt())["focus_items"]
    assert len(items) >= 3

    allowed_requirements = set(ABILITY_NAMES) | set(GAP_NAMES)
    for it in items:
        assert it["question"]
        assert it["evidence_status"] in ("sufficient", "insufficient", "none")
        assert it["related_requirement"] in allowed_requirements

    # 第一问必须锚定到一段真实经历标题，而不是"产品经理相关实习/项目"这类编造项。
    assert items[0]["related_experience"] in EXP_TITLES


def test_f14_motivation_question_uses_actual_job_and_company():
    items = _mock_f14(_f14_prompt(job_title="用户增长", company="麦浪文化"))["focus_items"]
    motivation = items[-1]
    assert "用户增长" in motivation["question"]
    assert "麦浪文化" in motivation["question"]


@pytest.mark.parametrize("job_title", [
    "用户增长", "产品运营", "内容运营", "数据分析师",
    "市场专员", "后端开发工程师", "视觉设计师", "星际探索员",
])
def test_f14_non_product_roles_never_get_product_wording(job_title):
    blob = _blob(_mock_f14(_f14_prompt(job_title=job_title, company="测试公司"))["focus_items"])
    for word in PRODUCT_ONLY_WORDS:
        assert word not in blob, f"{job_title} 的面试重点里出现了产品岗专属词：{word}"


def test_f14_answer_still_depends_on_role_family():
    """岗位族必须真的改变措辞，否则等于没改。"""
    ops = _mock_f14(_f14_prompt(job_title="用户增长"))["focus_items"][0]["question"]
    pm = _mock_f14(_f14_prompt(job_title="产品经理", company="测试公司"))["focus_items"][0]["question"]
    assert ops != pm


def test_f14_handles_missing_gaps_and_experiences():
    """入参缺 Gap / 缺经历时必须仍能产出结构完整的文案。"""
    items = _mock_f14(_f14_prompt(gaps=[], experiences=[]))["focus_items"]
    assert len(items) >= 3
    for it in items:
        assert it["question"]
        assert it["evidence_status"] in ("sufficient", "insufficient", "none")


def test_f14_no_scores_or_money():
    blob = _blob(_mock_f14(_f14_prompt())["focus_items"])
    assert "%" not in blob
    assert "评分" not in blob
    assert "薪资" not in blob


def test_f14_output_validates_against_schema():
    raw = MockProvider().chat_json(
        system_prompt="ignored",
        user_prompt=_f14_prompt(),
        output_schema=F14Output.model_json_schema(),
    )
    model = F14Output.model_validate(raw)
    assert len(model.focus_items) >= 3


# ===========================================================================
# F13 简历建议
# ===========================================================================
def test_f13_grounded_on_prompt_inputs():
    advices = _mock_f13(_f13_prompt())["advices"]
    assert len(advices) >= 4
    types = {a["advice_type"] for a in advices}
    assert types == {"highlight", "evidence_gap", "keyword", "weak_link"}

    allowed_gaps = set(GAP_NAMES) | set(ABILITY_NAMES) | {""}
    for a in advices:
        assert a["content"]
        assert a["related_gap"] in allowed_gaps
        assert a["severity"] in ("high", "medium", "low")

    highlight = next(a for a in advices if a["advice_type"] == "highlight")
    assert highlight["related_experience"] in EXP_TITLES

    evidence_gap = next(a for a in advices if a["advice_type"] == "evidence_gap")
    assert evidence_gap["related_gap"] in GAP_NAMES


def test_f13_keyword_advice_mentions_actual_job_title():
    advices = _mock_f13(_f13_prompt(job_title="用户增长"))["advices"]
    keyword = next(a for a in advices if a["advice_type"] == "keyword")
    assert "用户增长" in keyword["content"]


@pytest.mark.parametrize("job_title", [
    "用户增长", "产品运营", "内容运营", "数据分析师",
    "市场专员", "后端开发工程师", "视觉设计师", "星际探索员",
])
def test_f13_non_product_roles_never_get_product_wording(job_title):
    blob = _blob(_mock_f13(_f13_prompt(job_title=job_title, company="测试公司"))["advices"])
    for word in PRODUCT_ONLY_WORDS:
        assert word not in blob, f"{job_title} 的简历建议里出现了产品岗专属词：{word}"
    assert "产品经理相关实习/项目" not in blob


def test_f13_handles_missing_gaps_risks_experiences():
    advices = _mock_f13(_f13_prompt(gaps=[], risks=[], experiences=[]))["advices"]
    assert len(advices) >= 4
    for a in advices:
        assert a["content"]


def test_f13_output_validates_against_schema():
    raw = MockProvider().chat_json(
        system_prompt="ignored",
        user_prompt=_f13_prompt(),
        output_schema=F13Output.model_json_schema(),
    )
    model = F13Output.model_validate(raw)
    assert len(model.advices) >= 4


# ===========================================================================
# 已知未处理项（不属于本次改动范围，留档以免被误认为"已修"）
#
# `_mock_f9`（JD 解析）的 `is_pm` 分支关键词里有"用户"，所以任何含"用户"的 JD
# 都会被解析成 `title: 产品经理`。Demo seed 用 PUT /api/target-job/{id} 覆写了
# 岗位名，因此 Demo 看不到这个错配；但真实用户在页面上粘贴一段运营 JD 时，
# 解析草稿仍会显示"产品经理"。它同样属于 Mock 层的硬编码，若要一并修，
# 应当从 `user_prompt` 里读真实 JD 文本取 `【岗位名】`，而不是靠关键词猜。
# ===========================================================================
