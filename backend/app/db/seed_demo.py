"""Demo seed：注入「林小满」——一个完全虚构的应届生用户，用于在线 Demo。

设计原则
--------
* **复用真实业务 API 序列**（与 ``tests/test_e2e_user_journey.py`` 同源），
  不对 37 张表手写 ORM INSERT。数据由真实业务逻辑产生，因此自动满足全部
  数据库约束、状态机与用户隔离语义。
* **强制 Mock Provider**：seed 绝不调用真实 LLM。零成本、确定性、可离线重建。
* **幂等**：demo 用户已存在则跳过；``--force`` 先清理再重建。
* **相对时间**：所有日期/时间都相对"运行 seed 的那一刻"计算，
  Demo 放几个月后再打开也不会出现"投递是半年前、即将到来的面试永远是空的"。

产生的内容（覆盖六个工作区）
--------------------------
    职业画像 6 个能力标签 + 4 个兴趣 + 3 项优势 + 2 项风险 + 定位/倾向/动机/差距
    职业探索 6 个推荐方向 + 选定 1 个目标方向
    目标岗位 2 个（云枢科技·产品运营 / 麦浪文化·用户增长），均含 JD 解析 + 能力模型 + 匹配 + Gap
    求职准备 2 套备战计划（计划 / 任务 / 面试重点 3 条 / 简历建议 4 条）
    求职追踪 5 条投递（3 已 offer + 1 面试中 + 1 笔试）+ 5 条面试记录
    Offer   3 个（在比较中）+ 税后收入 + 四维定性评估 + 决策权重 + 对比分析

Demo 账号（仅含虚构数据）::

    demo@zhijizhibi.app / demo123456

用法::

    cd backend
    venv\\Scripts\\python.exe -m app.db.seed_demo            # 幂等，已存在则跳过
    venv\\Scripts\\python.exe -m app.db.seed_demo --force    # 删除并重建

两个刻意为之的取舍（都写在注释里，改数据前请先读）
------------------------------------------------
1. **能力名固定为六个**：MockProvider 的 F10 只对这六项返回判断
   （需求分析 / 沟通协调 / 项目管理 / 数据分析 / SQL / 行业经验）。若换成它不认识
   的能力名，会落到程序侧的关键词兜底路径上——而该路径当前存在缺陷（见
   ``match_service._keyword_relation``），会把所有能力判成 covered，导致 Demo
   看不到任何 Gap。因此这里保留能力名、只调整 level / weight / category，
   既能产生真实的 covered/partial/missing 分布，又不触碰任何业务逻辑。
2. **枚举值必须与业务状态机对齐**：投递状态、Offer 状态、面试状态/结果各有独立
   合法集合（见 ``tracking_service`` / ``offer_service``）。写错不会静默失败，
   接口会直接 422 —— 这是好事，但也意味着改数据时要去核对来源。
   另注意 ``_apply_interview_result`` 会把 result=pass/fail 的面试记录反向推成
   投递终态，所以"在途"投递的面试记录只能是 scheduled/pending 或 completed/pending。

已知局限（属于 AI 层，本次未改）
------------------------------
MockProvider 的 F13（简历建议）/ F14（面试重点）文案是为"产品经理"样例岗位写死的，
不读 JD 与用户经历，因此 Demo 里这两个页面会出现"为什么想做产品经理"这类与林小满
（运营方向）不符的措辞。真实 AI（``AI_PROVIDER=openai``）不会这样——它按 Prompt
结合 JD 与画像生成。在线 Demo 跑在 mock 上，这一点需要单独决定是否处理。
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

# --------------------------------------------------------------------------
# 环境必须在导入 app 之前固定：seed 一律走 Mock Provider，绝不联网、绝不产生费用。
# 用直接赋值（而非 setdefault）覆盖 .env 中的 AI_PROVIDER=openai，避免误用真实额度。
# --------------------------------------------------------------------------
os.environ["AI_PROVIDER"] = "mock"
os.environ["AI_BASE_URL"] = "http://localhost/mock"
os.environ["AI_API_KEY"] = "demo-seed-offline"
os.environ["AI_MODEL"] = "mock"
os.environ.setdefault("JWT_SECRET", "demo-seed-local-only")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db.base import Base, SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

DEMO_EMAIL = "demo@zhijizhibi.app"
DEMO_PASSWORD = "demo123456"
DEMO_NAME = "林小满"


# ==========================================================================
# HTTP helpers —— 任何非预期响应立即失败，避免"seed 成功了但数据是空的"
# ==========================================================================
def _day(offset_days: int) -> str:
    """相对今天的日期（YYYY-MM-DD）。Demo 数据一律用相对时间，永不过期。"""
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _moment(offset_days: int, hour_beijing: int = 14) -> str:
    """相对现在的 ISO 时间点（UTC），按北京时间整点换算。用于面试安排/投递时间。"""
    utc_hour = (hour_beijing - 8) % 24
    base = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return base.replace(hour=utc_hour, minute=0, second=0, microsecond=0).isoformat()


def _call(resp, path: str) -> Any:
    if resp.status_code != 200:
        raise RuntimeError(f"{path} -> HTTP {resp.status_code}: {resp.text[:400]}")
    return resp.json()


class Api:
    def __init__(self, client: TestClient):
        self.c = client
        self.headers: dict[str, str] = {}

    def post(self, path: str, body: dict | None = None) -> Any:
        return _call(self.c.post(path, json=body or {}, headers=self.headers), path)

    def put(self, path: str, body: dict | None = None) -> Any:
        return _call(self.c.put(path, json=body or {}, headers=self.headers), path)

    def get(self, path: str) -> Any:
        return _call(self.c.get(path, headers=self.headers), path)


# ==========================================================================
# 1. 经历 —— 林小满：市场营销专业，两段实习 + 一个校园项目（全部虚构）
# ==========================================================================
EXPERIENCE = {
    "education": [
        {"school": "江城大学", "major": "市场营销", "degree": "本科",
         "start": "2023-09", "end": "2027-06"}
    ],
    "internships": [
        {"company": "潮汐电商", "role": "内容运营实习生", "start": "2025-07", "end": "2025-09",
         "detail": "负责小红书与社群的选题策划，独立产出 40+ 篇内容；策划两次社群拉新活动，"
                   "把社群活跃率从 18% 提到 31%；每周整理内容数据复盘，输出选题方向建议。"},
        {"company": "维度广告", "role": "策略策划实习生", "start": "2026-01", "end": "2026-03",
         "detail": "参与 3 个消费品牌的 campaign 策划，负责竞品分析与用户访谈；"
                   "独立完成 12 份深度用户访谈，提炼出 5 条产品卖点洞察被团队采纳。"},
    ],
    "projects": [
        {"name": "校园社团招新增长实验", "role": "负责人",
         "desc": "设计问卷调研新生的社团选择动机，据此重构招新内容与社群裂变路径；"
                 "招新转化率从 12% 提升到 27%，复盘后沉淀了一套可复用的招新 SOP。"}
    ],
    "skills": [
        {"name": "用户调研", "level": 4},
        {"name": "内容策划", "level": 4},
        {"name": "社群运营", "level": 4},
        {"name": "数据分析", "level": 3},
        {"name": "SQL", "level": 2},
    ],
    "interests": ["用户增长", "内容运营", "消费品牌", "社群"],
}

# 访谈对话：模拟一个真实用户自然回答的过程（Mock 访谈引擎按轮次推进维度）
INTERVIEW_TURNS = [
    "我在潮汐电商做过内容运营实习，主要是选题策划和社群活动，那段时间我每天都会看用户评论。",
    "我比较擅长跟用户聊天，能从他们随口说的话里找到真正在意的东西，然后变成具体的选题。",
    "我更看重成长空间和团队氛围，希望做那种能直接看到用户反馈的工作，不太想整天写材料。",
    "我对消费品牌和内容平台都挺感兴趣的，未来想往用户增长这个方向走。",
]

# ==========================================================================
# 2. 画像润色 —— 通过 PUT /api/profile（真实 API）贴合人设
#    前端画像页读取：ability_tags / interest_tags / strengths / risks
#    以及 preference_infer 里的 positioning / tendencies / motivations / gaps
# ==========================================================================
PROFILE_POLISH = {
    "ability_tags": [
        {"tag": "用户调研", "level": 4, "confidence": 0.85, "evidence": "维度广告期间独立完成 12 份深度用户访谈"},
        {"tag": "内容策划", "level": 4, "confidence": 0.82, "evidence": "潮汐电商产出 40+ 篇内容，负责选题方向"},
        {"tag": "社群运营", "level": 4, "confidence": 0.8, "evidence": "策划两次社群拉新，活跃率 18% → 31%"},
        {"tag": "数据分析", "level": 3, "confidence": 0.72, "evidence": "每周整理内容数据复盘，输出选题建议"},
        {"tag": "活动策划", "level": 3, "confidence": 0.7, "evidence": "校园社团招新增长实验，转化率 12% → 27%"},
        {"tag": "SQL", "level": 2, "confidence": 0.6, "evidence": "课程与自学，能在指导下完成基础查询"},
    ],
    "interest_tags": [
        {"tag": "用户增长", "evidence": "访谈中提到想往用户增长方向发展"},
        {"tag": "内容运营", "evidence": "两段实习均围绕内容与社群展开"},
        {"tag": "消费品牌", "evidence": "参与 3 个消费品牌 campaign 策划"},
        {"tag": "社群", "evidence": "社团招新与社群运营经历"},
    ],
    "strengths": [
        {"item": "能把用户反馈转化为可执行的内容策略",
         "evidence": "潮汐电商期间依据评论区反馈调整选题方向，产出 40+ 篇内容"},
        {"item": "有结构化调研能力，能独立完成深度访谈并提炼洞察",
         "evidence": "维度广告独立完成 12 份用户访谈，提炼 5 条卖点洞察被采纳"},
        {"item": "有从 0 到 1 做增长实验并复盘的完整经验",
         "evidence": "校园社团招新把转化率从 12% 提升到 27%，并沉淀 SOP"},
    ],
    "risks": [
        {"item": "缺少数据驱动增长的完整项目经验",
         "evidence": "现有经历以内容与调研为主，尚未独立负责过以指标为核心的实验",
         "strategy": "找一个可量化的增长目标，完整跑一次「假设—实验—复盘」闭环并记录指标"},
        {"item": "跨部门推动项目的经验偏少",
         "evidence": "实习期间多为执行角色，未主导过跨团队协作",
         "strategy": "在校园项目或实习中主动承担协调角色，积累推动他人交付的经验"},
    ],
    "preference_infer": {
        "positioning": "擅长用内容与社群触达用户的运营型选手，正在把「读懂用户」这件事变成可复用的增长方法。",
        "tendencies": [
            {"axis": "探索性", "leaning": 0.72, "confidence": 0.7, "note": "愿意尝试新的增长玩法"},
            {"axis": "稳定性", "leaning": 0.38, "confidence": 0.6, "note": "更看重成长而非安稳"},
            {"axis": "自主性", "leaning": 0.65, "confidence": 0.65, "note": "喜欢自己把事推着走"},
            {"axis": "协作性", "leaning": 0.78, "confidence": 0.7, "note": "习惯和不同角色一起把事情做成"},
        ],
        "motivations": [
            "看到自己做的内容被真实用户使用和讨论",
            "把模糊的用户感受变成清晰、可执行的需求",
            "在快速试错里积累可复用的方法",
        ],
        "gaps": [
            {"item": "数据驱动增长的完整闭环经验",
             "why": "现有经历偏内容与调研，缺少以核心指标为目标的完整实验经验",
             "evidence": "两段实习均为执行角色"},
            {"item": "跨部门项目的推动经验",
             "why": "尚未主导过需要协调多方资源的项目",
             "evidence": "实习期间以配合为主"},
        ],
    },
}

# ==========================================================================
# 3. 目标岗位 ×2 —— 能力名固定（见模块 docstring），只调整 level/weight/category
# ==========================================================================
JD_A = """【产品运营】云枢科技
岗位职责：
1. 负责 B 端 SaaS 产品的用户运营，搭建用户分层与生命周期运营体系；
2. 通过用户调研与数据分析定位客户使用痛点，输出产品优化建议；
3. 策划并执行用户激活、留存相关的运营活动，跟踪核心指标；
4. 与产品、销售、客户成功团队协作，推动运营策略落地。
任职要求：
1. 本科及以上学历，市场营销、传播、管理类相关专业优先；
2. 具备用户调研与数据分析能力，能独立完成调研报告；
3. 有内容策划或社群运营经验者优先；
4. 良好的跨部门沟通与项目推动能力；
5. 熟悉 SQL 或数据分析工具者加分。"""

JD_B = """【用户增长】麦浪文化
岗位职责：
1. 负责内容平台的用户增长，设计并落地拉新、促活实验；
2. 分析用户行为数据，定位增长机会点并输出实验方案；
3. 结合内容与社群玩法，策划可复制的增长活动；
4. 沉淀增长方法论，并推动跨团队协作落地。
任职要求：
1. 本科及以上，有用户增长或内容运营相关经历优先；
2. 较强的用户洞察能力，能从数据中发现问题；
3. 了解 A/B 测试与增长实验设计；
4. 会使用 SQL 或 Python 处理数据者加分；
5. 对内容行业有真实兴趣。"""

TARGET_JOB_A = {
    "job_title": "产品运营",
    "company": "云枢科技",
    "industry": "互联网 / 企业服务",
    "responsibilities": [
        "搭建 B 端 SaaS 用户分层与生命周期运营体系",
        "通过用户调研与数据分析输出产品优化建议",
        "策划并执行用户激活与留存活动，跟踪核心指标",
        "协同产品、销售与客户成功团队推动策略落地",
    ],
    "abilities": [
        {"name": "需求分析", "category": "hard", "level": 4, "weight": 1.8, "requirement_type": "hard"},
        {"name": "数据分析", "category": "hard", "level": 3, "weight": 1.5, "requirement_type": "hard"},
        {"name": "沟通协调", "category": "soft", "level": 4, "weight": 1.4, "requirement_type": "soft"},
        {"name": "项目管理", "category": "soft", "level": 3, "weight": 1.2, "requirement_type": "soft"},
        {"name": "SQL", "category": "plus", "level": 2, "weight": 0.7, "requirement_type": "plus"},
        {"name": "行业经验", "category": "plus", "level": 3, "weight": 0.5, "requirement_type": "plus"},
    ],
}

TARGET_JOB_B = {
    "job_title": "用户增长",
    "company": "麦浪文化",
    "industry": "内容 / 文化传媒",
    "responsibilities": [
        "设计并落地内容平台的拉新与促活实验",
        "分析用户行为数据，定位增长机会点",
        "结合内容与社群玩法策划可复制的增长活动",
        "沉淀增长方法论并推动跨团队协作",
    ],
    "abilities": [
        {"name": "需求分析", "category": "hard", "level": 4, "weight": 1.6, "requirement_type": "hard"},
        {"name": "数据分析", "category": "hard", "level": 4, "weight": 1.7, "requirement_type": "hard"},
        {"name": "沟通协调", "category": "hard", "level": 4, "weight": 1.3, "requirement_type": "hard"},
        {"name": "项目管理", "category": "soft", "level": 3, "weight": 1.1, "requirement_type": "soft"},
        {"name": "SQL", "category": "plus", "level": 3, "weight": 0.8, "requirement_type": "plus"},
        {"name": "行业经验", "category": "hard", "level": 3, "weight": 1.0, "requirement_type": "hard"},
    ],
}

# ==========================================================================
# 4. 投递 + 面试 + Offer ×3
#   company / job_title / city 与 Offer 对应；salary 为元/月
#
#   status 必须落在 tracking_service._VALID_STATUSES 内：
#     drafted / applied / written_test / interviewing / offer_received / rejected / withdrawn
#   这里刻意做成完整漏斗（拿到 offer ×3 + 在途 ×2），而不是清一色 offer_received，
#   否则追踪工作区没有任何"进行中"的语义，Demo 看起来像一张死表。
#
#   所有时间都用「相对现在」的天数表达（applied_days_ago / offset_days），
#   而不是写死日期——Demo 可能在任何时候被打开，写死日期会迅速过期，
#   让"即将到来的面试"永远是空的、"投递时间"变成几个月前。
# ==========================================================================
APPLICATIONS = [
    # 已拿 offer 的三条（与下方 OFFERS 一一对应）
    {"company": "云枢科技", "job_title": "产品运营", "city": "杭州",
     "status": "offer_received", "note": "已收到书面 Offer，一周内答复", "job": "A",
     "applied_days_ago": 38},
    {"company": "麦浪文化", "job_title": "用户增长", "city": "上海",
     "status": "offer_received", "note": "口头 Offer 已确认，等 HR 走流程", "job": "B",
     "applied_days_ago": 33},
    {"company": "星野数据", "job_title": "内容运营", "city": "杭州",
     "status": "offer_received", "note": "已收到 Offer，薪资待谈", "job": None,
     "applied_days_ago": 30},
    # 仍在流程中的两条（不与目标岗位关联，纯投递记录）
    {"company": "晨帆智能", "job_title": "运营管培生", "city": "深圳",
     "status": "interviewing", "note": "一面已结束，等面试结果通知", "job": None,
     "applied_days_ago": 12},
    {"company": "若水教育", "job_title": "用户运营", "city": "北京",
     "status": "written_test", "note": "笔试已通过，已约二面", "job": None,
     "applied_days_ago": 9},
]

# 面试记录：status ∈ {scheduled, completed, cancelled}，result ∈ {pending, pass, fail}
#   「app」= APPLICATIONS 的下标。
#
# ⚠️ 不要给"在途"投递配 result=pass/fail 的面试记录：
#   tracking_service._apply_interview_result 会在更新面试结果时
#   pass -> offer_received、fail -> rejected，把在途记录直接推到终态。
#   （创建接口不触发该联动，但我们仍按"语义正确"来配：
#    已完成但公司未出结果 -> completed + pending，这是真实存在且不触发联动的组合。）
INTERVIEWS = [
    # 云枢科技（已 offer）：一面 + 二面均通过，时间线完整
    {"app": 0, "round": "一面", "interview_type": "业务面", "status": "completed",
     "result": "pass", "interviewer": "运营负责人", "offset_days": -26,
     "note": "围绕用户分层与调研方法提问，重点追问了我做过的用户访谈项目"},
    {"app": 0, "round": "二面", "interview_type": "总监面", "status": "completed",
     "result": "pass", "interviewer": "运营总监", "offset_days": -21,
     "note": "问了对 B 端运营的理解，现场让我设计一次客户激活活动"},
    # 麦浪文化（已 offer）：一面通过
    {"app": 1, "round": "一面", "interview_type": "业务面", "status": "completed",
     "result": "pass", "interviewer": "增长负责人", "offset_days": -18,
     "note": "聊了内容平台的增长玩法，问我怎么设计一次拉新实验"},
    # 晨帆智能（在途）：一面完成、结果未出 —— 不触发状态联动
    {"app": 3, "round": "一面", "interview_type": "业务面", "status": "completed",
     "result": "pending", "interviewer": "管培生项目负责人", "offset_days": -5,
     "note": "群面 + 单面，围绕案例分析和数据解读，结果待通知"},
    # 若水教育（在途）：已约二面 —— 让追踪页的"即将到来的面试"不为空
    {"app": 4, "round": "二面", "interview_type": "HR 面", "status": "scheduled",
     "result": "pending", "interviewer": "HRBP", "offset_days": 4,
     "note": "待参加，准备一下自我介绍和对加班/出差的态度"},
]

# Offer 的 status 必须落在 offer_service._VALID_STATUSES 内：
#   draft / active / accepted / rejected / expired
# 三个 Offer 都还没做决定，因此是 active（"在比较中"）——这正好对应 Demo 想展示的
# 「三份 Offer 摆在一起做决策」场景。若填 accepted，该 Offer 会变成终态并退出可比较范围。
OFFERS = [
    {"company": "云枢科技", "job_title": "产品运营", "city": "杭州",
     "industry": "互联网 / 企业服务",
     "salary": {"monthly_base": 13000, "annual_bonus_months": 3, "sign_on": 10000},
     "special_deduction": 1500, "status": "active",
     "note": "B 端 SaaS，团队 8 人，直属 leader 来自大厂", "application": 0, "job": "A",
     "public_signals": ["B 端 SaaS 赛道，客户续费率是核心指标", "团队规模较小，个人负责面较广"],
     "user_notes": "面试感受很好，业务逻辑清晰，但担心 B 端节奏偏慢、成长需要时间。"},
    {"company": "麦浪文化", "job_title": "用户增长", "city": "上海",
     "industry": "内容 / 文化传媒",
     "salary": {"monthly_base": 15000, "annual_bonus_months": 2},
     "special_deduction": 1500, "status": "active",
     "note": "内容平台，增长团队刚组建，直接向增长负责人汇报", "application": 1, "job": "B",
     "public_signals": ["内容行业增长岗位，指标压力通常较大", "团队新组建，流程尚在磨合"],
     "user_notes": "方向最匹配我想做的事，薪资也最高，但听说加班多、指标压力大。"},
    {"company": "星野数据", "job_title": "内容运营", "city": "杭州",
     "industry": "数据服务",
     "salary": {"monthly_base": 11000, "annual_bonus_months": 4},
     "special_deduction": 1500, "status": "active",
     "note": "数据服务公司，内容团队成熟，流程规范", "application": 2, "job": None,
     "public_signals": ["公司业务稳定，团队流程成熟", "内容岗位偏执行，自主空间有限"],
     "user_notes": "最稳定的一份，但工作内容偏执行，担心成长速度。"},
]

# Offer 的 status 必须落在 offer_service._VALID_STATUSES 内：
#   draft / active / accepted / rejected / expired
# 三个 Offer 都还没做决定，因此是 active（"在比较中"）——这正好对应 Demo 想展示的
# 「三份 Offer 摆在一起做决策」场景。若填 accepted，该 Offer 会变成终态并退出可比较范围。
OFFERS = [
    {"company": "云枢科技", "job_title": "产品运营", "city": "杭州",
     "industry": "互联网 / 企业服务",
     "salary": {"monthly_base": 13000, "annual_bonus_months": 3, "sign_on": 10000},
     "special_deduction": 1500, "status": "active",
     "note": "B 端 SaaS，团队 8 人，直属 leader 来自大厂", "application": 0, "job": "A",
     "public_signals": ["B 端 SaaS 赛道，客户续费率是核心指标", "团队规模较小，个人负责面较广"],
     "user_notes": "面试感受很好，业务逻辑清晰，但担心 B 端节奏偏慢、成长需要时间。"},
    {"company": "麦浪文化", "job_title": "用户增长", "city": "上海",
     "industry": "内容 / 文化传媒",
     "salary": {"monthly_base": 15000, "annual_bonus_months": 2},
     "special_deduction": 1500, "status": "active",
     "note": "内容平台，增长团队刚组建，直接向增长负责人汇报", "application": 1, "job": "B",
     "public_signals": ["内容行业增长岗位，指标压力通常较大", "团队新组建，流程尚在磨合"],
     "user_notes": "方向最匹配我想做的事，薪资也最高，但听说加班多、指标压力大。"},
    {"company": "星野数据", "job_title": "内容运营", "city": "杭州",
     "industry": "数据服务",
     "salary": {"monthly_base": 11000, "annual_bonus_months": 4},
     "special_deduction": 1500, "status": "active",
     "note": "数据服务公司，内容团队成熟，流程规范", "application": 2, "job": None,
     "public_signals": ["公司业务稳定，团队流程成熟", "内容岗位偏执行，自主空间有限"],
     "user_notes": "最稳定的一份，但工作内容偏执行，担心成长速度。"},
]

# 决策权重：成长优先（贴合林小满的画像倾向）
DECISION_WEIGHTS = {
    "weights": {"economic": 15, "disposable": 10, "workload": 10,
                "stability": 10, "growth": 40, "match": 15},
    "preset_name": "growth",
}


# ==========================================================================
# 清理（--force）：不依赖 SQLite 的 FK pragma（默认关闭），按依赖逆序显式清理
# ==========================================================================
def purge_demo_user(email: str) -> bool:
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        if uid is None:
            return False
        for table in reversed(Base.metadata.sorted_tables):
            if "user_id" in table.c:
                db.execute(delete(table).where(table.c.user_id == uid))
        db.execute(delete(User.__table__).where(User.__table__.c.id == uid))
        db.commit()
        return True


def demo_user_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email)) is not None


# ==========================================================================
# 主流程 —— 全程复用真实 API，与 tests/test_e2e_user_journey.py 同源
# ==========================================================================
def seed(client: TestClient) -> dict:
    api = Api(client)

    # ---- 注册 ----
    reg = _call(client.post("/api/auth/register", json={
        "email": DEMO_EMAIL, "password": DEMO_PASSWORD, "name": DEMO_NAME,
    }), "/api/auth/register")
    api.headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # ---- Onboarding：访谈会话 → 经历 → 对话 → 生成画像 ----
    api.post("/api/onboarding/session")
    api.post("/api/onboarding/bootstrap", {"entry_method": "scratch"})
    api.post("/api/experience", EXPERIENCE)
    for msg in INTERVIEW_TURNS:
        api.post("/api/onboarding/step", {"message": msg})
    finalized = api.post("/api/onboarding/finalize")
    if not finalized.get("profile_id"):
        raise RuntimeError("finalize 未产生 profile_id，画像生成失败")

    # ---- 画像润色（真实 API）----
    api.put("/api/profile", PROFILE_POLISH)

    # ---- 职业探索：拿程序排序后的方向，选定目标方向 ----
    state = api.get("/api/explore/state")
    recs = state.get("recommendations") or []
    if not recs:
        raise RuntimeError("探索推荐为空，无法继续")
    direction_id = recs[0]["direction_id"]
    api.post("/api/explore/target", {"direction_id": direction_id})

    # ---- 目标岗位 ×2：创建 → 解析 → 定制能力模型 → 匹配/Gap ----
    target_jobs: dict[str, dict] = {}
    for key, jd, spec in (("A", JD_A, TARGET_JOB_A), ("B", JD_B, TARGET_JOB_B)):
        created = api.post("/api/target-job/create",
                           {"raw_jd": jd, "direction_id": direction_id})
        tj_id = created["target_job_id"]
        parsed = api.post("/api/target-job/parse", {
            "target_job_id": tj_id, "raw_jd": jd,
            "job_title": spec["job_title"], "company": spec["company"],
        })
        ability_model = dict(parsed["target_job"]["ability_model"])
        ability_model.update({
            "company": spec["company"],
            "title": spec["job_title"],
            "industry": spec["industry"],
            "responsibilities": spec["responsibilities"],
            "abilities": spec["abilities"],
        })
        api.put(f"/api/target-job/{tj_id}", {
            "ability_model": ability_model,
            "job_title": spec["job_title"],
            "company": spec["company"],
            "industry": spec["industry"],
            "responsibilities": spec["responsibilities"],
        })
        target_jobs[key] = {"id": tj_id, **spec}

    # ---- 求职准备：备战 Agent 一键编排（匹配 → Gap → 计划 → 面试重点 → 简历建议）----
    for key in ("A", "B"):
        tj_id = target_jobs[key]["id"]
        api.post(f"/api/prepare/battle-plan/{tj_id}")

    # ---- 求职追踪：5 条投递（3 已 offer + 2 在途）+ 5 条面试记录 ----
    app_ids: list[int] = []
    for item in APPLICATIONS:
        job_key = item["job"]
        payload: dict[str, Any] = {
            "company": item["company"], "job_title": item["job_title"],
            "city": item["city"], "status": item["status"], "note": item["note"],
            "source": "官网投递",
            "applied_at": _day(-item["applied_days_ago"]),
        }
        if job_key:
            payload["target_job_id"] = target_jobs[job_key]["id"]
        created = api.post("/api/tracking/applications", payload)
        app_ids.append(created["application_id"])

    for spec in INTERVIEWS:
        api.post(f"/api/tracking/applications/{app_ids[spec['app']]}/interviews", {
            "round": spec["round"], "interview_type": spec["interview_type"],
            "status": spec["status"], "result": spec["result"],
            "interviewer": spec["interviewer"], "note": spec["note"],
            "scheduled_at": _moment(spec["offset_days"], spec.get("hour", 14)),
        })

    # ---- Offer ×3：创建 → 税后计算 → 定性评估 ----
    offer_ids: list[int] = []
    for spec in OFFERS:
        job_key = spec["job"]
        payload: dict[str, Any] = {
            "company": spec["company"], "job_title": spec["job_title"],
            "city": spec["city"], "industry": spec["industry"],
            "salary": spec["salary"], "special_deduction": spec["special_deduction"],
            "status": spec["status"], "note": spec["note"],
            "application_id": app_ids[spec["application"]],
        }
        if job_key:
            payload["target_job_id"] = target_jobs[job_key]["id"]
        created = api.post("/api/offer/applications", payload)
        offer_id = created["offer_id"]
        offer_ids.append(offer_id)
        # F19 税后收入（程序计算）
        api.post(f"/api/offer/applications/{offer_id}/salary_calc", {})
        # F21 四维定性档位（Mock AI）
        api.post(f"/api/offer/applications/{offer_id}/assess", {
            "public_signals": spec["public_signals"],
            "user_notes": spec["user_notes"],
        })

    # ---- 决策权重 + F23/F24 对比分析 ----
    api.put("/api/offer/weights", DECISION_WEIGHTS)
    comparison = api.get("/api/offer/comparison")

    return {
        "direction_id": direction_id,
        "target_jobs": target_jobs,
        "application_ids": app_ids,
        "offer_ids": offer_ids,
        "comparison_offers": len(comparison.get("offers", []) or []),
    }


def verify(client: TestClient, headers: dict[str, str]) -> list[str]:
    """逐步校验每个工作区都能正常读取（Demo 可浏览性的硬性检查）。"""
    api = Api(client)
    api.headers = headers
    checks: list[tuple[str, bool, str]] = []

    profile = api.get("/api/profile")
    checks.append(("职业画像", bool(profile.get("ability_tags")),
                   f"{len(profile.get('ability_tags') or [])} 个能力标签"))

    explore = api.get("/api/explore/state")
    checks.append(("职业探索", bool(explore.get("recommendations")),
                   f"{len(explore.get('recommendations') or [])} 个推荐方向"))

    tj_home = api.get("/api/target-job/home")
    checks.append(("目标岗位", bool(tj_home.get("has_target")),
                   f"{len(tj_home.get('items') or [])} 个岗位 / "
                   f"当前匹配分 {((tj_home.get('match_summary') or {}).get('total_score'))}"))

    prep = api.get("/api/prepare/home")
    checks.append(("求职准备", bool(prep.get("prep_plan")),
                   f"{len(prep.get('tasks') or [])} 个准备任务 / "
                   f"{len(prep.get('gaps') or [])} 条能力差距"))

    interview = api.get("/api/prepare/interview")
    checks.append(("面试重点", bool(interview.get("interview_focus")),
                   f"{len(interview.get('interview_focus') or [])} 条面试问题"))

    resume = api.get("/api/prepare/resume")
    checks.append(("简历建议", bool(resume.get("resume_advice")),
                   f"{len(resume.get('resume_advice') or [])} 条简历建议"))

    tracking = api.get("/api/tracking/overview")
    upcoming = tracking.get("upcoming_interviews") or []
    checks.append(("求职追踪", (tracking.get("total") or 0) > 0,
                   f"{tracking.get('total')} 条投递 / {len(upcoming)} 场待面"))
    checks.append(("投递状态分布",
                   len([k for k, v in (tracking.get("counts") or {}).items() if v > 0]) >= 2,
                   "、".join(f"{k}×{v}" for k, v in (tracking.get("counts") or {}).items() if v)))

    offers = api.get("/api/offer/applications")
    checks.append(("Offer 列表", (offers.get("total") or 0) >= 3,
                   f"{offers.get('total')} 个 Offer"))

    comparison = api.get("/api/offer/comparison")
    checks.append(("Offer 对比", bool(comparison.get("offers")),
                   f"{len(comparison.get('offers') or [])} 个参与对比"))

    lines: list[str] = []
    failed = 0
    for name, ok, detail in checks:
        mark = "OK  " if ok else "FAIL"
        if not ok:
            failed += 1
        lines.append(f"  [{mark}] {name:<10} {detail}")
    # 先输出再抛错：否则失败时看不到到底哪一项挂了，排查还得重跑一遍 seed。
    print("\n工作区数据校验:")
    for line in lines:
        print(line, flush=True)
    if failed:
        raise RuntimeError(f"{failed} 项工作区数据校验失败")
    return lines


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    force = "--force" in argv

    from app.api.auth import _login_limiter, _register_limiter

    # 限流器是进程级单例；反复重建会触发注册限流，seed 前显式重置。
    _register_limiter.reset_all()
    _login_limiter.reset_all()

    if demo_user_exists(DEMO_EMAIL):
        if not force:
            print(f"demo 用户已存在（{DEMO_EMAIL}），跳过。强制重建请加 --force")
            return 0
        purged = purge_demo_user(DEMO_EMAIL)
        print(f"已清理旧 demo 数据（--force）: {purged}")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        # lifespan 已完成迁移与种子（方向库 / 城市成本）
        summary = seed(client)
        _print_summary(summary)

        # 用 demo 账号真实登录一次，拿 token 做校验（同时验证密码可用）
        login = _call(client.post("/api/auth/login", json={
            "identifier": DEMO_EMAIL, "password": DEMO_PASSWORD,
        }), "/api/auth/login")
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        verify(client, headers)

    print("\n模型调用: 0 次（全程 Mock Provider，未联网、未产生费用）")
    return 0


def _print_summary(summary: dict) -> None:
    print("\nDemo 数据构建完成（林小满 / 全部虚构）")
    print(f"  账号: {DEMO_EMAIL}  密码: {DEMO_PASSWORD}")
    print(f"  选定方向 id: {summary['direction_id']}")
    for key, tj in summary["target_jobs"].items():
        print(f"  目标岗位 {key}: {tj['company']} · {tj['job_title']}（id={tj['id']}）")
    print(f"  投递: {len(summary['application_ids'])} 条    "
          f"Offer: {len(summary['offer_ids'])} 个    "
          f"参与对比: {summary['comparison_offers']} 个")


if __name__ == "__main__":
    raise SystemExit(main())
