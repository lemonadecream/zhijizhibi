"""用户视角 E2E：完整职业决策链旅程（Mock Provider）。

一个真实应届生用户从头走到尾：
  Onboarding 访谈 → Career Profile → Explore 选方向 → Target Job（绑定方向 + JD 匹配）
  → Prepare（按岗位加载 + 多岗位切换）→ Tracking（投递关联岗位）→ Offer（评估）

本轮（P0/P1 收口）重点检查的 7 项：
  1. Explore 选择的方向是否真正传到 TargetJob（direction_id 绑定 + 持久化）
  2. TargetJob 是否绑定正确 direction_id（创建/重载一致）
  3. 多个 Target Job 是否可在 Prepare 中切换（显式 target_job_id）
  4. Prepare 是否针对当前选择的岗位加载（plan/gaps/匹配全部对应）
  5. AI 结果是否明确区分 真实 AI / Mock / fallback（/api/config + 各结果 ai_status）
  6. 页面刷新后上下文是否仍然成立（重载 GET 返回一致）
  7. 不同用户数据是否严格隔离

运行于 SQLite + Mock AI Provider（与既有套件一致），属于 Mock E2E。
真实 Provider E2E 需环境配置 AI_PROVIDER=openai + 有效 Key，见完成报告第 6 节。
"""
from __future__ import annotations

import uuid


def _register(client, tag):
    email = f"e2e-{tag}-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "secret123", "name": "应届生"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _experience_payload():
    return {
        "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
        "internships": [{"company": "阿里", "role": "产品经理", "start": "2022", "end": "2022", "detail": "需求分析"}],
        "projects": [{"name": "增长项目", "role": "产品", "desc": "用户调研与数据复盘"}],
        "skills": [{"name": "需求分析", "level": 4}, {"name": "数据分析", "level": 3}],
        "interests": ["产品设计", "用户研究"],
    }


def _onboarding_to_profile(client, h):
    """真实用户路径：访谈会话 -> 填写经历 -> 两轮对话 -> 生成画像(F2)。"""
    s = client.post("/api/onboarding/session", headers=h)
    assert s.status_code == 200
    b = client.post("/api/onboarding/bootstrap", json={"entry_method": "scratch"}, headers=h)
    assert b.status_code == 200
    assert client.post("/api/experience", json=_experience_payload(), headers=h).status_code == 200
    for msg in ["我做过产品实习，会写需求文档", "我比较擅长沟通和数据复盘"]:
        r = client.post("/api/onboarding/step", json={"message": msg}, headers=h)
        assert r.status_code == 200, r.text
    f = client.post("/api/onboarding/finalize", headers=h)
    assert f.status_code == 200, f.text
    body = f.json()
    assert body["profile_id"] is not None
    return body


def _full_target_job(client, h, raw, title, company):
    """目标岗位全流程：创建(可带方向) -> 解析 -> 确认 -> 匹配。返回 (tj, match, gaps)。"""
    tj = client.post("/api/target-job/create", json={"raw_jd": raw}, headers=h).json()
    tid = tj["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tid, "raw_jd": raw, "job_title": title, "company": company},
        headers=h,
    ).json()
    am = p["target_job"]["ability_model"]
    client.put(
        f"/api/target-job/{tid}",
        json={"ability_model": am, "job_title": title, "company": company,
              "industry": am.get("industry", ""), "responsibilities": am.get("responsibilities", [])},
        headers=h,
    )
    m = client.post(f"/api/target-job/{tid}/match", json={}, headers=h)
    assert m.status_code == 200, m.text
    return tid, tj, m.json()["match"], m.json()["gaps"]


SAMPLE_JD_A = """
【产品经理】 某某科技
职责：负责 B 端SaaS 产品的需求分析与规划。
要求：产品需求分析能力（hard）、沟通协调能力（soft）、SQL 数据分析经验（plus）。
"""
SAMPLE_JD_B = """
【数据产品经理】 某某数科
职责：负责数据产品指标体系搭建。
要求：数据分析能力（hard）、项目管理（soft）、Python 经验（plus）。
"""


def test_user_journey_end_to_end(client):
    # ---------- 注册 + Onboarding → 画像 ----------
    h = _register(client, "a")
    _onboarding_to_profile(client, h)

    # 检查点 5：/api/config 明确暴露 provider 与可用性（Mock → 演示模式）
    cfg = client.get("/api/config", headers=h).json()
    assert set(cfg.keys()) == {"ai_provider", "ai_available"}
    assert cfg["ai_provider"] == "mock"
    assert cfg["ai_available"] is False

    # ---------- Explore：推荐 + 选方向 ----------
    st = client.get("/api/explore/state", headers=h).json()
    assert st["has_profile"] is True
    recs = st["recommendations"]
    assert len(recs) >= 1
    d1 = recs[0]["direction_id"]
    # AI 解释状态可区分（mock 下 reason_status 仍为 "ok"，徽标按 provider 显示演示模式）
    assert recs[0]["reason_status"] in ("ok", "fallback")
    tgt = client.post("/api/explore/target", json={"direction_id": d1}, headers=h).json()
    assert tgt["state"]["target_direction_id"] == d1

    # ---------- TargetJob：绑定方向（检查点 1、2） ----------
    c1 = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD_A, "direction_id": d1}, headers=h).json()
    assert c1["direction_id"] == d1, "方向必须写入 target_job.direction_id"
    tj1 = c1["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj1, "raw_jd": SAMPLE_JD_A, "job_title": "产品经理", "company": "某某科技"},
        headers=h,
    ).json()
    am = p["target_job"]["ability_model"]
    client.put(
        f"/api/target-job/{tj1}",
        json={"ability_model": am, "job_title": "产品经理", "company": "某某科技",
              "industry": am.get("industry", ""), "responsibilities": am.get("responsibilities", [])},
        headers=h,
    )
    m = client.post(f"/api/target-job/{tj1}/match", json={}, headers=h)
    assert m.status_code == 200
    match1 = m.json()["match"]
    gaps1 = m.json()["gaps"]
    assert match1["ai_status"] in ("ok", "fallback")  # 检查点 5：单结果 AI 状态

    # 检查点 6（刷新）：重载后方向上下文仍在（DB 持久）
    reloaded = client.get(f"/api/target-job/{tj1}", headers=h).json()
    assert reloaded["direction_id"] == d1

    # ---------- Prepare：生成计划 + 按岗位加载（检查点 4、5） ----------
    gen = client.post("/api/prepare/generate", json={"target_job_id": tj1}, headers=h)
    assert gen.status_code == 200, gen.text
    assert gen.json()["ai_status"] in ("ok", "fallback")
    home1 = client.get("/api/prepare/home", params={"target_job_id": tj1}, headers=h).json()
    assert home1["target_job"]["target_job_id"] == tj1
    assert home1["prep_plan"] is not None
    assert home1["prep_plan"]["ai_status"] in ("ok", "fallback")  # P0-1: plan AI 状态透传
    assert {t["ability"] for t in home1["tasks"]} == {g["ability"] for g in gaps1}  # plan 消费对应岗位 gap

    # ---------- Prepare：多岗位切换（检查点 3、4） ----------
    tj2, _, _, _ = _full_target_job(client, h, SAMPLE_JD_B, "数据产品经理", "某某数科")
    home_b = client.get("/api/prepare/home", params={"target_job_id": tj2}, headers=h).json()
    assert home_b["target_job"]["target_job_id"] == tj2
    home_a_again = client.get("/api/prepare/home", params={"target_job_id": tj1}, headers=h).json()
    assert home_a_again["target_job"]["target_job_id"] == tj1
    # 无参数 → 默认最新（tj2）
    default = client.get("/api/prepare/home", headers=h).json()
    assert default["target_job"]["target_job_id"] == tj2
    # 刷新保持：URL 参数语义由前端承载，后端显式 id 重载一致（检查点 6）

    # ---------- Tracking：投递关联岗位 ----------
    app = client.post(
        "/api/tracking/applications",
        json={"company": "某某科技", "job_title": "产品经理", "city": "杭州", "target_job_id": tj1},
        headers=h,
    ).json()
    assert app["target_job_id"] == tj1

    # ---------- Offer：创建 + 评估（F21/F24） ----------
    of = client.post(
        "/api/offer/applications",
        json={"company": "某某科技", "job_title": "产品经理", "city": "杭州",
              "salary": {"monthly_base": 22000, "annual_bonus_months": 3},
              "special_deduction": 2000, "application_id": app["application_id"], "target_job_id": tj1},
        headers=h,
    ).json()
    ass = client.post(f"/api/offer/applications/{of['offer_id']}/assess", json={}, headers=h).json()
    assert ass["ai_status"] in ("ok", "fallback")  # 检查点 5

    # ---------- 检查点 7：用户隔离 ----------
    h2 = _register(client, "b")
    _onboarding_to_profile(client, h2)
    assert client.get("/api/target-job/home", headers=h2).json()["has_target"] is False
    assert client.get("/api/prepare/home", headers=h2).json()["has_target"] is False
    assert client.get("/api/tracking/overview", headers=h2).json()["total"] == 0
    assert client.get("/api/offer/applications", headers=h2).json()["total"] == 0
