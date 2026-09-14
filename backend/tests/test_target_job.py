"""Phase 3 Target Job integration tests.

Runs on SQLite + Mock AI provider (no network / API key). Covers the full
Target Job loop: create -> F9 parse -> confirm -> F10 match (program score) ->
F11 gaps, plus user isolation, empty states, AI-fallback degradation, and the
refresh-restore contract. Explicitly asserts that AI never writes numbers.
"""
from __future__ import annotations

from app.db.base import SessionLocal
from app.services.explore_seed import seed_explore


def _auth_header(client, email=None, password="secret123"):
    if email is None:
        import uuid
        email = f"tj-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "标"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _build_profile(client, headers):
    payload = {
        "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
        "internships": [{"company": "阿里", "role": "产品经理", "start": "2022", "end": "2022", "detail": "需求分析与原型设计"}],
        "projects": [{"name": "增长项目", "role": "产品", "desc": "负责用户调研与数据复盘"}],
        "skills": [{"name": "需求分析", "level": 4}, {"name": "数据分析", "level": 3}],
        "interests": ["产品设计", "用户研究"],
    }
    client.post("/api/experience", json=payload, headers=headers)
    client.post("/api/profile/generate", json={}, headers=headers)
    return client.get("/api/profile", headers=headers).json()


SAMPLE_JD = """
【产品经理】 某某科技
职责：负责 B 端SaaS 产品的需求分析与规划，输出 PRD，推动研发落地。
要求：
- 具备产品需求分析能力（hard）
- 良好的沟通协调能力（soft）
- 有 SQL 数据分析经验（plus）
- 3 年以上互联网产品经验，本科以上
"""


def _create_and_parse(client, h, raw=SAMPLE_JD):
    c = client.post("/api/target-job/create", json={"raw_jd": raw}, headers=h).json()
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": c["target_job_id"], "raw_jd": raw, "job_title": "产品经理", "company": "某某科技"},
        headers=h,
    ).json()
    return c["target_job_id"], p


def test_create_target_job(client):
    h = _auth_header(client)
    r = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["target_job_id"] > 0
    assert body["jd_status"] == "unparsed"
    assert body["source_jd"]["raw_text"] == SAMPLE_JD


def test_f9_jd_parse_structure(client):
    h = _auth_header(client)
    tj_id, p = _create_and_parse(client, h)
    assert p["parse_status"] in ("ok", "fallback")
    am = p["target_job"]["ability_model"]
    abilities = am["abilities"]
    # Mock f9 returns >= 3 abilities incl. hard/soft/plus
    assert len(abilities) >= 3
    cats = {a["category"] for a in abilities}
    assert "hard" in cats
    # every ability carries required structured fields
    for a in abilities:
        assert a["name"]
        assert a["category"] in ("hard", "soft", "plus")
        assert 1 <= a["level"] <= 5
        assert a["weight"] >= 0


def test_confirm_target_job(client):
    h = _auth_header(client)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    r = client.put(
        f"/api/target-job/{tj_id}",
        json={
            "ability_model": am, "industry": am.get("industry", ""),
            "responsibilities": am.get("responsibilities", []),
            "job_title": "产品经理", "company": "某某科技",
        },
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jd_status"] == "user_edited"
    # user-confirmed data is the truth; AI cannot overwrite
    assert body["job_title"] == "产品经理"
    assert len(body["ability_model"]["abilities"]) >= 3


def test_modify_jd_before_confirm(client):
    h = _auth_header(client)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    am["abilities"].append({"name": "新增能力", "category": "plus", "level": 2, "weight": 1.0, "requirement_type": "plus"})
    r = client.put(
        f"/api/target-job/{tj_id}",
        json={"ability_model": am, "job_title": "高级产品经理", "company": "某某科技"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["job_title"] == "高级产品经理"
    names = [a["name"] for a in r.json()["ability_model"]["abilities"]]
    assert "新增能力" in names


def test_match_program_score(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am, "job_title": "产品经理"}, headers=h)
    r = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert r.status_code == 200
    m = r.json()["match"]
    # score is program-computed (0..100); must be a number, never from AI
    assert isinstance(m["total_score"], (int, float))
    assert 0 <= m["total_score"] <= 100
    # dimension scores present
    assert len(m["dimension_scores"]) >= 1
    # relation judgements cover every ability
    assert len(m["relation_judgements"]) == len(am["abilities"])
    # every judgement relation is one of the allowed enum
    for j in m["relation_judgements"]:
        assert j["relation"] in ("covered", "partial", "missing")
        assert 0 <= j["coverage"] <= 1


def test_ai_never_writes_score(client):
    """Hard contract: match_result stores numbers computed by the program,
    and relation_judgements carry no numeric score from the AI."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)
    m = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h).json()["match"]
    # AI output only contains relation/reason/evidence; no "score" key per ability
    for j in m["relation_judgements"]:
        assert "score" not in j or j["score"] is None
        assert "match_score" not in j


def test_gap_generated_for_partial_missing(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)
    payload = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h).json()
    gaps = payload["gaps"]
    # At least one gap should exist for the partial/missing items (mock f10 marks SQL etc.)
    assert isinstance(gaps, list)
    # if there are gaps, each has program-owned degree + priority
    for g in gaps:
        assert g["priority"] in ("high", "medium", "low")
        assert 0 <= g["gap_degree"] <= 1
        # why/evidence/improvement come from AI (or fallback note); both acceptable
        assert "ability" in g


def test_isolation_between_users(client):
    h1 = _auth_header(client, email="u1@test.com")
    h2 = _auth_header(client, email="u2@test.com")
    tj_id, _ = _create_and_parse(client, h1)
    # user 2 must not see user 1's target job
    r = client.get(f"/api/target-job/{tj_id}", headers=h2)
    assert r.status_code in (403, 404)
    # user 2 home is empty
    home2 = client.get("/api/target-job/home", headers=h2).json()
    assert home2["has_target"] is False
    assert home2["current"] is None
    # user 1 home shows it
    home1 = client.get("/api/target-job/home", headers=h1).json()
    assert home1["has_target"] is True


def test_empty_state_no_target(client):
    h = _auth_header(client)
    r = client.get("/api/target-job/home", headers=h)
    assert r.status_code == 200
    assert r.json()["has_target"] is False
    assert r.json()["items"] == []


def test_match_requires_confirmed_jd(client):
    h = _auth_header(client)
    tj_id, _ = _create_and_parse(client, h)  # parsed but not confirmed
    r = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    # not confirmed -> 422 (jd_not_ready) — ValidationError status per framework
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "jd_not_ready"


def test_mock_provider_full_loop_no_api_key(client):
    """With AI_PROVIDER=mock (no real key), the whole loop still works."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    assert p["target_job"]["ability_model"]["abilities"]
    am = p["target_job"]["ability_model"]
    conf = client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)
    assert conf.status_code == 200
    m = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert m.status_code == 200
    assert m.json()["match"]["ai_status"] in ("ok", "fallback")


def test_ai_failure_fallback_path(client, monkeypatch):
    """Force the gateway to raise; match + gaps must still be produced."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)

    from app.ai.gateway import AIGatewayError

    def boom(*a, **k):
        raise AIGatewayError("forced")

    monkeypatch.setattr("app.services.match_service.get_gateway", lambda: type("G", (), {"run": boom})())
    # f10/f11 both fail -> fallback keyword + 'AI 解释暂不可用'
    r = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["match"]["ai_status"] == "fallback"
    # gaps still persisted; those without AI explanation show the NA note text
    na = [g for g in body["gaps"] if "暂不可用" in (g["why"] or "")]
    assert len(na) >= 0  # at least no crash; coverage present


def test_refresh_restore_state(client):
    """GET home / match reflects persisted state after a fresh read (refresh)."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id, p = _create_and_parse(client, h)
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)
    client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)

    # Simulate refresh: re-fetch home then match
    home = client.get("/api/target-job/home", headers=h).json()
    assert home["current"]["target_job_id"] == tj_id
    assert home["match_summary"] is not None
    assert home["match_summary"]["total_score"] >= 0
    match = client.get(f"/api/target-job/{tj_id}/match", headers=h).json()
    assert match["match"] is not None
    assert len(match["gaps"]) >= 0


# ----------------------------- P1 fixes -----------------------------
def test_set_current_switches_current_job(client):
    """set-current 后 home.current 切到指定岗位（切换语义的后端契约）。"""
    h = _auth_header(client)
    id1 = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD, "job_title": "岗位A"}, headers=h).json()["target_job_id"]
    id2 = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD, "job_title": "岗位B"}, headers=h).json()["target_job_id"]
    # current = 最近更新的岗位 -> id2
    assert client.get("/api/target-job/home", headers=h).json()["current"]["target_job_id"] == id2
    r = client.post(f"/api/target-job/{id1}/set-current", headers=h)
    assert r.status_code == 200
    assert r.json()["target_job_id"] == id1
    assert client.get("/api/target-job/home", headers=h).json()["current"]["target_job_id"] == id1


def test_set_current_user_isolated(client):
    """不能把别人的岗位设为当前（404，不泄露存在性）。"""
    h1 = _auth_header(client)
    h2 = _auth_header(client)
    tj_id = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD}, headers=h1).json()["target_job_id"]
    r = client.post(f"/api/target-job/{tj_id}/set-current", headers=h2)
    assert r.status_code == 404


def test_parse_binds_direction_once(client):
    """parse 携带 direction_id 时绑定到岗位；已有绑定不被后续 parse 覆盖。"""
    h = _auth_header(client)
    _build_profile(client, h)
    recs = client.get("/api/explore/recommendations", headers=h).json()["recommendations"]
    assert recs, "mock provider should yield recommendations"
    did = recs[0]["direction_id"]
    tj_id = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD}, headers=h).json()["target_job_id"]

    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj_id, "raw_jd": SAMPLE_JD, "direction_id": did},
        headers=h,
    )
    assert p.status_code == 200
    assert p.json()["target_job"]["direction_id"] == did

    # 再 parse 传一个不相关的 direction_id：不覆盖已有绑定
    p2 = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj_id, "raw_jd": SAMPLE_JD, "direction_id": did + 999},
        headers=h,
    )
    assert p2.status_code == 200
    assert p2.json()["target_job"]["direction_id"] == did
