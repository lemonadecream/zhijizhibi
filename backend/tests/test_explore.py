"""Phase 2 Explore integration tests.

Runs on SQLite + Mock AI provider (no network / API key). Covers the full
Explore loop: profile -> recommendations -> natural-language preference ->
exclude -> compare (2/3/4) -> detail drill-down -> target migration, plus the
AI-unavailable degradation path and empty/edge states.
"""
from __future__ import annotations

from app.db.base import SessionLocal
from app.services.explore_seed import seed_explore


def _auth_header(client, email="explore@test.com", password="secret123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "探"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _build_profile(client, headers):
    """Create experiences + generate a ready career profile (Mock F2)."""
    payload = {
        "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
        "internships": [{"company": "阿里", "role": "后端", "start": "2022", "end": "2022", "detail": "服务端开发"}],
        "projects": [{"name": "推荐系统", "role": "开发", "desc": "用 Python 做召回排序"}],
        "skills": [{"name": "Python", "level": 4}, {"name": "系统设计", "level": 3}],
        "interests": ["后端开发", "数据分析"],
    }
    client.post("/api/experience", json=payload, headers=headers)
    client.post("/api/profile/generate", json={}, headers=headers)
    return client.get("/api/profile", headers=headers).json()


def _seed(client):
    with SessionLocal() as db:
        seed_explore(db)


def test_no_profile_returns_has_profile_false(client):
    h = _auth_header(client)
    r = client.get("/api/explore/state", headers=h)
    assert r.status_code == 200
    assert r.json()["has_profile"] is False
    assert r.json()["recommendations"] == []


def test_recommendations_returned_and_ranked(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    r = client.get("/api/explore/state", headers=h)
    body = r.json()
    assert body["has_profile"] is True
    recs = body["recommendations"]
    assert len(recs) >= 3
    # sorted by score desc
    scores = [x["score"] for x in recs]
    assert scores == sorted(scores, reverse=True)
    # every active rec carries a reason (mock F4) + match basis
    for rec in recs:
        assert rec["reason"]
        assert rec["match_basis"]


def test_natural_language_preference_reranks(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    before = client.get("/api/explore/state", headers=h).json()["recommendations"]
    # Express a preference that should boost the 金融/风控 line.
    r = client.post(
        "/api/explore/preferences/text",
        json={"text": "我不做纯技术，比较看重稳定，想去金融行业"},
        headers=h,
    )
    assert r.status_code == 200
    after = r.json()["recommendations"]
    # avoid "纯技术" should push the tech-expert line's score down (or exclude-ish)
    tech_before = next(x for x in before if x["name"] == "技术专家线")
    tech_after = next((x for x in after if x["name"] == "技术专家线"), None)
    # tech line either still present with lower score, or dropped relative to finance
    finance_after = next((x for x in after if x["name"] == "金融 / 风控线"), None)
    if tech_after and finance_after:
        assert tech_after["score"] <= tech_before["score"] + 1e-6
    # parsed preferences persisted
    assert r.json()["state"]["preferences"]["prefer_fields"]
    assert "纯技术" in r.json()["state"]["preferences"]["avoid_keywords"]


def test_exclude_direction(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    recs = client.get("/api/explore/state", headers=h).json()["recommendations"]
    did = recs[0]["direction_id"]
    r = client.post(f"/api/explore/directions/{did}/exclude", json={"excluded": True}, headers=h)
    assert r.status_code == 200
    assert did in r.json()["state"]["excluded_direction_ids"]
    # excluded direction no longer in active recommendations
    new_recs = r.json()["recommendations"]
    assert all(x["direction_id"] != did for x in new_recs)
    # re-include
    r2 = client.post(f"/api/explore/directions/{did}/exclude", json={"excluded": False}, headers=h)
    assert did not in r2.json()["state"]["excluded_direction_ids"]


def test_compare_toggle_and_set(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    recs = client.get("/api/explore/state", headers=h).json()["recommendations"]
    d1, d2, d3 = recs[0]["direction_id"], recs[1]["direction_id"], recs[2]["direction_id"]

    # toggle two
    client.post(f"/api/explore/directions/{d1}/compare", json={}, headers=h)
    client.post(f"/api/explore/directions/{d2}/compare", json={}, headers=h)
    # compare view with 2
    cmp = client.get("/api/explore/compare", headers=h).json()
    assert len(cmp["rows"]) == 2
    assert cmp["advice"]  # neutral advice generated

    # set 3 explicitly
    r = client.post("/api/explore/compare", json={"direction_ids": [d1, d2, d3]}, headers=h)
    assert r.status_code == 200
    cmp3 = client.get("/api/explore/compare", headers=h).json()
    assert len(cmp3["rows"]) == 3

    # max 4 enforced on direct set
    d4 = recs[3]["direction_id"]
    r4 = client.post("/api/explore/compare", json={"direction_ids": [d1, d2, d3, d4, recs[4]["direction_id"]]}, headers=h)
    assert r4.status_code == 422


def test_detail_drilldown(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    recs = client.get("/api/explore/state", headers=h).json()["recommendations"]
    did = recs[0]["direction_id"]
    d = client.get(f"/api/explore/directions/{did}", headers=h).json()
    assert d["industries"]
    assert d["jobs"]
    ind_id = d["industries"][0]["id"]
    ind = client.get(f"/api/explore/industries/{ind_id}", headers=h).json()
    assert ind["jobs"]
    job_id = ind["jobs"][0]["id"]
    job = client.get(f"/api/explore/jobs/{job_id}", headers=h).json()
    assert job["required_abilities"]


def test_set_target_direction(client):
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    recs = client.get("/api/explore/state", headers=h).json()["recommendations"]
    did = recs[0]["direction_id"]
    r = client.post("/api/explore/target", json={"direction_id": did}, headers=h)
    assert r.status_code == 200
    assert r.json()["target_direction_id"] == did
    assert did in r.json()["state"]["candidate_direction_ids"]


def test_ai_unavailable_degrades(client, monkeypatch):
    """Force F4 to fail -> reason should still be produced via fallback."""
    import app.ai.gateway as gw_mod

    def _boom(self, name, input_dict):
        from app.errors.exceptions import AIGatewayError
        raise AIGatewayError("forced", task=name)

    monkeypatch.setattr(gw_mod.AIGateway, "run", _boom)
    h = _auth_header(client)
    _build_profile(client, h)
    _seed(client)
    recs = client.get("/api/explore/state", headers=h).json()["recommendations"]
    # every rec must have a non-empty reason even when AI fails (template fallback)
    for rec in recs:
        assert rec["reason"]
        assert rec["reason_status"] == "fallback"
