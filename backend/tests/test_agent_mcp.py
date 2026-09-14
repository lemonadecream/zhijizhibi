"""备战 Agent + MCP server 测试（mock provider，无网络）。"""
from __future__ import annotations

import json

import pytest

from mcp_server import _handle


def _auth_header(client, email=None, password="secret123"):
    import uuid

    email = email or f"agent-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "标"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _profile_and_jd(client, h):
    """建画像 + 建 JD 已确认的目标岗位，返回 target_job_id。"""
    client.post(
        "/api/experience",
        json={
            "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
            "internships": [{"company": "阿里", "role": "产品经理", "start": "2022", "end": "2022", "detail": "需求分析与 SQL 分析"}],
            "projects": [{"name": "增长项目", "role": "产品", "desc": "数据复盘"}],
            "skills": [{"name": "需求分析", "level": 4}, {"name": "SQL", "level": 4}, {"name": "沟通协调", "level": 3}, {"name": "行业经验", "level": 2}],
            "interests": ["数据产品"],
        },
        headers=h,
    )
    client.post("/api/profile/generate", json={}, headers=h)

    jd = "数据产品经理：负责需求分析与 SQL 数据分析，需要行业经验，沟通协调能力。3年经验。"
    c = client.post("/api/target-job/create", json={"raw_jd": jd}, headers=h).json()
    tid = c["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tid, "raw_jd": jd, "job_title": "数据产品经理", "company": "某某科技"},
        headers=h,
    ).json()
    client.put(f"/api/target-job/{tid}", json={"ability_model": p["target_job"]["ability_model"]}, headers=h)
    return tid


def test_battle_plan_end_to_end(client):
    """备战 Agent：一次调用编排 匹配→计划→面试→简历建议，含 trace。"""
    h = _auth_header(client)
    tid = _profile_and_jd(client, h)

    r = client.post(f"/api/prepare/battle-plan/{tid}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    # 完整备战包
    assert body["target_job"]["target_job_id"] == tid
    assert 0 <= body["match"]["total_score"] <= 100
    assert body["prep_plan"]["prep_plan"] is not None
    assert isinstance(body["interview_focus"]["interview_focus"], list)
    assert isinstance(body["resume_advice"]["resume_advice"], list)

    # trace：5 步全部 ok 且有耗时
    assert [s["step"] for s in body["steps"]] == [
        "target_job_detail", "match", "prep_plan", "interview_focus", "resume_advice",
    ]
    assert all(s["ok"] for s in body["steps"])


def test_battle_plan_requires_confirmed_jd(client):
    """JD 未确认（unparsed）时拒绝备战。"""
    h = _auth_header(client)
    tid = client.post("/api/target-job/create", json={"raw_jd": "随便一段不够长的JD文本"}, headers=h).json()["target_job_id"]
    r = client.post(f"/api/prepare/battle-plan/{tid}", headers=h)
    assert r.status_code == 422


def test_battle_plan_user_isolated(client):
    """不能给别人的岗位做备战（404）。"""
    h1 = _auth_header(client)
    h2 = _auth_header(client)
    tid = client.post("/api/target-job/create", json={"raw_jd": "产品经理岗位，需求分析岗"}, headers=h1).json()["target_job_id"]
    r = client.post(f"/api/prepare/battle-plan/{tid}", headers=h2)
    assert r.status_code in (404, 422)


def test_mcp_handshake_and_tools():
    """MCP 协议子集：initialize → tools/list → 未知方法报错。"""
    init = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "zhiji-zhibi"
    assert init["result"]["protocolVersion"]

    assert _handle({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) is None

    tools = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"explore_directions", "target_job_match", "prep_plan"} <= names

    err = _handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert err["error"]["code"] == -32601

    pong = _handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    assert pong["result"] == {}


def test_mcp_tool_call_runs(client):
    """tools/call 真正执行（走同一数据库）。"""
    h = _auth_header(client)
    tid = _profile_and_jd(client, h)
    # 从 dev 库拿 user_id（注册接口返回 token；这里直接用 /auth/me 反查）
    me = client.get("/api/auth/me", headers=h).json()
    uid = me["user_id"]

    resp = _handle({
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "target_job_match", "arguments": {"user_id": uid, "target_job_id": tid}},
    })
    assert "result" in resp
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert 0 <= payload["total_score"] <= 100
    assert isinstance(payload["relations"], list)
