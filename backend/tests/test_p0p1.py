"""P0/P1 收口修复的针对性测试 (Phase 0-6 收口).

Covers the three fixes that were out of scope for earlier phase tests:
  * P0-1: GET /api/config exposes {ai_provider, ai_available} honestly and
          NEVER leaks secrets (API key / token / endpoint).
  * P0-2: Explore -> Target Job direction carry: createTargetJob persists the
          incoming direction_id; getTargetJob returns it.
  * P1-2: /api/prepare/home honours an explicit ?target_job_id (no longer
          silently always using latest); prep_plan.ai_status is surfaced.

These run on SQLite + Mock AI provider (no network / API key), consistent with
the rest of the suite.
"""
from __future__ import annotations

import app.api.config as config_module


# ----------------------------- shared helpers (mirror test_prepare) -----------------------------
def _auth_header(client, email=None, password="secret123"):
    if email is None:
        import uuid
        email = f"p0p1-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "标"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _build_profile(client, headers):
    payload = {
        "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
        "internships": [{"company": "阿里", "role": "产品经理", "start": "2022", "end": "2022", "detail": "需求分析"}],
        "projects": [{"name": "增长项目", "role": "产品", "desc": "用户调研"}],
        "skills": [{"name": "需求分析", "level": 4}, {"name": "数据分析", "level": 3}],
        "interests": ["产品设计", "用户研究"],
    }
    client.post("/api/experience", json=payload, headers=headers)
    client.post("/api/profile/generate", json={}, headers=headers)
    return client.get("/api/profile", headers=headers).json()


SAMPLE_JD_A = """
【产品经理】 公司A
职责：负责 B 端SaaS 产品的需求分析与规划。
要求：具备产品需求分析能力（hard）、良好的沟通协调能力（soft）、有 SQL 数据分析经验（plus）。
"""
SAMPLE_JD_B = """
【数据产品经理】 公司B
职责：负责数据产品的指标体系搭建。
要求：数据分析能力（hard）、项目管理（soft）、有 Python 经验（plus）。
"""


def _create_parse_confirm_match(client, h, raw):
    c = client.post("/api/target-job/create", json={"raw_jd": raw}, headers=h).json()
    tj_id = c["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj_id, "raw_jd": raw, "job_title": "岗位", "company": "公司"},
        headers=h,
    ).json()
    am = p["target_job"]["ability_model"]
    client.put(
        f"/api/target-job/{tj_id}",
        json={"ability_model": am, "job_title": "岗位", "company": "公司",
              "industry": am.get("industry", ""), "responsibilities": am.get("responsibilities", [])},
        headers=h,
    )
    m = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert m.status_code == 200
    return tj_id


# ----------------------------- P0-1: config endpoint -----------------------------
def test_config_shape_and_mock_unavailable(client):
    """Default test env is mock provider -> ai_available must be False."""
    h = _auth_header(client)
    r = client.get("/api/config", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"ai_provider", "ai_available"}
    assert body["ai_provider"] == "mock"
    assert body["ai_available"] is False


def test_config_no_secret_leak(client):
    """The endpoint must never return keys/tokens/endpoints."""
    h = _auth_header(client)
    r = client.get("/api/config", headers=h)
    body = r.json()
    raw = str(body)
    # conftest sets AI_API_KEY="test-key"; it must not appear anywhere.
    assert "test-key" not in raw
    assert "AI_API_KEY" not in raw
    assert "Bearer" not in raw
    assert "sk-" not in raw


def test_config_ai_available_true_for_real_provider_with_key(client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(config_module.settings, "AI_API_KEY", "real-key")
    r = client.get("/api/config", headers=_auth_header(client))
    assert r.json()["ai_available"] is True


def test_config_ai_available_false_for_real_provider_without_key(client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(config_module.settings, "AI_API_KEY", "")
    r = client.get("/api/config", headers=_auth_header(client))
    assert r.json()["ai_available"] is False


def test_config_ai_available_false_even_if_mock_has_key(client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "AI_PROVIDER", "mock")
    monkeypatch.setattr(config_module.settings, "AI_API_KEY", "some-key")
    r = client.get("/api/config", headers=_auth_header(client))
    assert r.json()["ai_available"] is False


# ----------------------------- P0-2: Explore -> Target Job direction carry -----------------------------
def test_target_job_create_persists_direction_id(client):
    h = _auth_header(client)
    # get a real direction id from the seeded explore graph (needs a profile)
    _build_profile(client, h)
    recs = client.get("/api/explore/recommendations", headers=h).json()["recommendations"]
    assert recs, "expected seeded directions"
    direction_id = recs[0]["direction_id"]

    # create a target job carrying that direction
    c = client.post(
        "/api/target-job/create",
        json={"raw_jd": SAMPLE_JD_A, "direction_id": direction_id},
        headers=h,
    ).json()
    assert c["direction_id"] == direction_id

    # it must survive a reload via getTargetJob
    full = client.get(f"/api/target-job/{c['target_job_id']}", headers=h).json()
    assert full["direction_id"] == direction_id


def test_target_job_create_without_direction_id_ok(client):
    h = _auth_header(client)
    c = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD_A}, headers=h).json()
    assert c["direction_id"] is None


# ----------------------------- P1-2: Prepare honours explicit target_job_id -----------------------------
def test_prepare_home_respects_target_job_id(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_a = _create_parse_confirm_match(client, h, SAMPLE_JD_A)
    tj_b = _create_parse_confirm_match(client, h, SAMPLE_JD_B)

    home_a = client.get("/api/prepare/home", params={"target_job_id": tj_a}, headers=h).json()
    assert home_a["has_target"] is True
    assert home_a["has_match"] is True
    assert home_a["target_job"]["target_job_id"] == tj_a

    home_b = client.get("/api/prepare/home", params={"target_job_id": tj_b}, headers=h).json()
    assert home_b["target_job"]["target_job_id"] == tj_b

    # without an explicit id it falls back to the latest (tj_b, created later)
    home_default = client.get("/api/prepare/home", headers=h).json()
    assert home_default["target_job"]["target_job_id"] == tj_b


def test_prepare_home_plan_ai_status_surfaced(client):
    """P0-1 transparency: the plan carries its AI status on reload (not just at
    generate time)."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h, SAMPLE_JD_A)
    client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)

    home = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home["prep_plan"] is not None
    assert home["prep_plan"]["ai_status"] in ("ok", "fallback")
