"""Explore knowledge-base seed (Phase 2).

Idempotent seeder run at app startup (or via ``seed_explore``). It populates the
``industry`` / ``job`` / ``direction`` knowledge base with realistic,
*interrelated* data so recommendations have something real to match against —
without any external AI call at runtime.

Relationships (the program reads these; AI never writes them):
  industry 1──* job
  industry *──* direction  (direction.industry_ids)
  job     *──* direction   (direction.job_ids)
  direction.core_abilities / attributes / work_styles / not_good_for / growth_path
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.explore import Direction, Industry, Job


# --- Industries -----------------------------------------------------------------
INDUSTRIES: list[dict] = [
    {
        "slug": "internet",
        "name": "互联网 / 软件",
        "description": "以软件产品、平台与在线服务为核心的行业，节奏快、技术密集、岗位类型最丰富。",
        "traits": ["高成长", "技术密集", "变化快", "远程友好"],
        "work_styles": ["敏捷迭代", "跨职能协作", "数据驱动"],
    },
    {
        "slug": "finance",
        "name": "金融 / 金融科技",
        "description": "银行、证券、保险与新兴金融科技，强调合规、稳健与量化能力。",
        "traits": ["高稳定", "强合规", "薪酬高", "压力大"],
        "work_styles": ["流程规范", "风险导向", "精细严谨"],
    },
    {
        "slug": "manufacturing",
        "name": "智能制造 / 硬件",
        "description": "硬件研发、嵌入式、工业软件与智能工厂，软硬结合，落地周期长。",
        "traits": ["实体落地", "工程导向", "稳健", "产业链长"],
        "work_styles": ["工程化", "团队协作", "长期主义"],
    },
    {
        "slug": "consumer",
        "name": "消费 / 内容 / 文创",
        "description": "电商、内容社区、品牌与文创，强调用户感知、创意与增长。",
        "traits": ["用户导向", "创意密集", "增长驱动", "节奏快"],
        "work_styles": ["用户共创", "内容驱动", "快速试错"],
    },
]

# --- Jobs -----------------------------------------------------------------------
# industry_slug -> jobs
JOBS: dict[str, list[dict]] = {
    "internet": [
        {"slug": "backend", "name": "后端工程师", "description": "设计与实现服务端逻辑、接口与数据存储。",
         "required_abilities": ["编程能力", "系统设计", "数据库", "问题拆解"], "entry_barrier": 3,
         "work_styles": ["独立钻研", "团队协作", "逻辑严谨"]},
        {"slug": "frontend", "name": "前端工程师", "description": "实现用户界面与交互，连接设计与后端。",
         "required_abilities": ["编程能力", "用户体验", "界面实现"], "entry_barrier": 3,
         "work_styles": ["用户导向", "协作", "快速迭代"]},
        {"slug": "pm", "name": "产品经理", "description": "定义产品方向、梳理需求、推动跨团队落地。",
         "required_abilities": ["沟通协调", "需求分析", "商业判断", "项目管理"], "entry_barrier": 3,
         "work_styles": ["跨职能协作", "用户导向", "决策驱动"]},
        {"slug": "data", "name": "数据工程师 / 分析师", "description": "搭建数据管道、做分析与可视化，支撑决策。",
         "required_abilities": ["数据分析", "编程能力", "SQL", "统计"], "entry_barrier": 3,
         "work_styles": ["逻辑严谨", "数据驱动"]},
        {"slug": "algo", "name": "算法 / AI 工程师", "description": "研究与落地机器学习、推荐、NLP 等模型。",
         "required_abilities": ["数学建模", "编程能力", "机器学习", "科研"], "entry_barrier": 4,
         "work_styles": ["独立钻研", "探索性", "深度专业"]},
    ],
    "finance": [
        {"slug": "fin_pd", "name": "金融产品经理", "description": "设计金融相关产品与流程，兼顾合规与体验。",
         "required_abilities": ["金融知识", "需求分析", "合规意识", "项目管理"], "entry_barrier": 3,
         "work_styles": ["流程规范", "风险导向", "协作"]},
        {"slug": "quant", "name": "量化研究 / 开发", "description": "用模型与代码做定价、交易与风控。",
         "required_abilities": ["数学建模", "编程能力", "金融知识", "统计"], "entry_barrier": 5,
         "work_styles": ["深度专业", "独立钻研", "精细严谨"]},
        {"slug": "risk", "name": "风控 / 合规", "description": "评估与控制业务风险，确保合规。",
         "required_abilities": ["金融知识", "风险判断", "合规意识"], "entry_barrier": 3,
         "work_styles": ["流程规范", "风险导向", "精细严谨"]},
    ],
    "manufacturing": [
        {"slug": "embedded", "name": "嵌入式工程师", "description": "开发软硬件结合的系统与设备固件。",
         "required_abilities": ["编程能力", "硬件基础", "系统设计", "工程化"], "entry_barrier": 3,
         "work_styles": ["工程化", "团队协作", "长期主义"]},
        {"slug": "hw_pm", "name": "硬件 / 项目产品经理", "description": "统筹硬件产品从定义到量产。",
         "required_abilities": ["项目管理", "硬件基础", "沟通协调", "需求分析"], "entry_barrier": 4,
         "work_styles": ["工程化", "跨职能协作", "长期主义"]},
        {"slug": "industrial_sw", "name": "工业软件工程师", "description": "为制造场景开发 CAD/MES/控制类软件。",
         "required_abilities": ["编程能力", "系统设计", "行业理解"], "entry_barrier": 4,
         "work_styles": ["工程化", "逻辑严谨", "团队协作"]},
    ],
    "consumer": [
        {"slug": "growth", "name": "增长 / 运营", "description": "通过内容与活动驱动用户与业务增长。",
         "required_abilities": ["用户洞察", "沟通协调", "数据分析", "创意"], "entry_barrier": 2,
         "work_styles": ["用户导向", "快速试错", "内容驱动"]},
        {"slug": "ux", "name": "用户体验设计师", "description": "研究用户、设计可用且好用的产品体验。",
         "required_abilities": ["用户体验", "视觉/交互", "用户洞察", "沟通协调"], "entry_barrier": 3,
         "work_styles": ["用户导向", "创意", "协作"]},
        {"slug": "content", "name": "内容 / 社区运营", "description": "运营内容生态与用户社区。",
         "required_abilities": ["内容创作", "用户洞察", "沟通协调"], "entry_barrier": 2,
         "work_styles": ["内容驱动", "用户共创", "快速试错"]},
    ],
}

# --- Directions -----------------------------------------------------------------
# attributes are KNOWLEDGE-BASE values (0..1) for the program recommender.
DIRECTIONS: list[dict] = [
    {
        "slug": "tech-expert",
        "name": "技术专家线",
        "summary": "深耕工程与代码，成为某一技术领域不可替代的骨干。",
        "description": "沿着工程师路径持续精进，从功能开发走向架构与深度技术攻关。适合喜欢把问题做成系统、享受技术成长的人。",
        "industries": ["internet", "manufacturing"],
        "jobs": ["backend", "frontend", "embedded", "industrial_sw", "algo"],
        "core_abilities": ["编程能力", "系统设计", "问题拆解", "数据分析"],
        "work_styles": ["独立钻研", "逻辑严谨", "深度专业"],
        "attributes": {"growth": 0.8, "stability": 0.6, "autonomy": 0.7, "social": 0.4, "creativity": 0.5},
        "not_good_for": ["非常排斥写代码", "极度偏好与人高频沟通而非钻研", "希望快速转向管理"],
        "growth_path": "初级工程师 → 中高级工程师 → 技术专家 / 架构师",
    },
    {
        "slug": "product",
        "name": "产品管理线",
        "summary": "定义产品方向、连接用户与技术，对结果负责。",
        "description": "在用户需求、商业目标与技术可行性之间做权衡，推动产品落地。适合既理解人、又能做判断、享受跨团队推进的人。",
        "industries": ["internet", "finance", "consumer"],
        "jobs": ["pm", "fin_pd", "hw_pm"],
        "core_abilities": ["沟通协调", "需求分析", "商业判断", "项目管理"],
        "work_styles": ["跨职能协作", "用户导向", "决策驱动"],
        "attributes": {"growth": 0.8, "stability": 0.5, "autonomy": 0.6, "social": 0.85, "creativity": 0.7},
        "not_good_for": ["不喜欢与人频繁沟通", "希望只专注技术实现", "对商业和责任结果无感"],
        "growth_path": "产品助理 → 产品经理 → 高级产品经理 / 产品负责人",
    },
    {
        "slug": "data-ai",
        "name": "数据 / AI 线",
        "summary": "用数据与模型发现问题、预测趋势、驱动智能。",
        "description": "从数据工程到算法建模，用量化方法解决业务问题。适合逻辑强、喜欢探索与验证、愿意持续学习新技术的人。",
        "industries": ["internet", "finance", "manufacturing"],
        "jobs": ["data", "algo", "quant"],
        "core_abilities": ["数据分析", "数学建模", "编程能力", "机器学习"],
        "work_styles": ["数据驱动", "独立钻研", "探索性"],
        "attributes": {"growth": 0.9, "stability": 0.55, "autonomy": 0.7, "social": 0.4, "creativity": 0.6},
        "not_good_for": ["排斥数学与统计", "希望工作高度确定性", "不喜欢长期钻研"],
        "growth_path": "数据分析师 → 数据/算法工程师 → 资深算法专家",
    },
    {
        "slug": "finance-line",
        "name": "金融 / 风控线",
        "summary": "在稳健与合规的框架内做专业判断与价值管理。",
        "description": "围绕资金、风险与合规展开专业工作，强调严谨与责任心。适合稳重、细致、对数字敏感的人。",
        "industries": ["finance"],
        "jobs": ["fin_pd", "quant", "risk"],
        "core_abilities": ["金融知识", "风险判断", "合规意识", "数学建模"],
        "work_styles": ["流程规范", "风险导向", "精细严谨"],
        "attributes": {"growth": 0.6, "stability": 0.9, "autonomy": 0.5, "social": 0.5, "creativity": 0.3},
        "not_good_for": ["讨厌流程与合规约束", "希望高自由度试错", "对数字与风险不敏感"],
        "growth_path": "风控/分析师 → 高级专员 → 风控/业务负责人",
    },
    {
        "slug": "user-growth",
        "name": "用户增长 / 运营线",
        "summary": "靠对用户与内容的感知，驱动业务与社区持续生长。",
        "description": "通过内容、活动与数据运营拉动增长，离用户最近。适合敏感、有创意、喜欢快速试错的人。",
        "industries": ["consumer", "internet"],
        "jobs": ["growth", "content", "ux"],
        "core_abilities": ["用户洞察", "沟通协调", "创意", "数据分析"],
        "work_styles": ["用户导向", "快速试错", "内容驱动"],
        "attributes": {"growth": 0.8, "stability": 0.45, "autonomy": 0.55, "social": 0.9, "creativity": 0.85},
        "not_good_for": ["排斥数据复盘", "不喜欢与人/内容打交道", "偏好稳定少变"],
        "growth_path": "运营/增长专员 → 运营负责人 → 业务负责人",
    },
    {
        "slug": "hardware-eng",
        "name": "硬件 / 嵌入式线",
        "summary": "做软硬结合的系统，把产品真正落到实体。",
        "description": "围绕设备、固件与工业软件展开工程实现，周期长而扎实。适合喜欢看得见摸得着的工程成果、耐得住长周期的人。",
        "industries": ["manufacturing"],
        "jobs": ["embedded", "hw_pm", "industrial_sw"],
        "core_abilities": ["编程能力", "硬件基础", "工程化", "系统设计"],
        "work_styles": ["工程化", "团队协作", "长期主义"],
        "attributes": {"growth": 0.6, "stability": 0.8, "autonomy": 0.6, "social": 0.5, "creativity": 0.5},
        "not_good_for": ["只想做纯互联网软件", "不喜欢长落地周期", "排斥硬件相关"],
        "growth_path": "嵌入式/软件工程师 → 系统工程师 → 技术负责人",
    },
]


def seed_explore(db: Session) -> dict:
    """Idempotently seed the knowledge base. Returns a small count report."""
    created = {"industry": 0, "job": 0, "direction": 0}

    # Industries
    ind_by_slug: dict[str, Industry] = {}
    for d in INDUSTRIES:
        ind = db.scalar(select(Industry).where(Industry.slug == d["slug"]))
        if ind is None:
            ind = Industry(
                slug=d["slug"], name=d["name"], description=d["description"],
                traits=d["traits"], work_styles=d["work_styles"],
            )
            db.add(ind)
            db.flush()
            created["industry"] += 1
        ind_by_slug[d["slug"]] = ind

    # Jobs (need industry ids)
    job_by_slug: dict[str, Job] = {}
    for ind_slug, jobs in JOBS.items():
        industry = ind_by_slug[ind_slug]
        for j in jobs:
            job = db.scalar(select(Job).where(Job.slug == j["slug"]))
            if job is None:
                job = Job(
                    slug=j["slug"], industry_id=industry.id, name=j["name"],
                    description=j["description"], required_abilities=j["required_abilities"],
                    entry_barrier=j["entry_barrier"], work_styles=j["work_styles"],
                )
                db.add(job)
                db.flush()
                created["job"] += 1
            job_by_slug[j["slug"]] = job

    # Directions (link industries + jobs)
    for d in DIRECTIONS:
        direction = db.scalar(select(Direction).where(Direction.slug == d["slug"]))
        if direction is None:
            direction = Direction(
                slug=d["slug"], name=d["name"], summary=d["summary"], description=d["description"],
                industry_ids=[ind_by_slug[s].id for s in d["industries"] if s in ind_by_slug],
                job_ids=[job_by_slug[s].id for s in d["jobs"] if s in job_by_slug],
                core_abilities=d["core_abilities"], work_styles=d["work_styles"],
                attributes=d["attributes"], not_good_for=d["not_good_for"],
                growth_path=d["growth_path"],
            )
            db.add(direction)
            db.flush()
            created["direction"] += 1

    db.commit()
    return created
