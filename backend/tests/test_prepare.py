"""Phase 4 Preparation workspace integration tests.

Runs on SQLite + Mock AI provider (no network / API key). Covers the full
Phase 4 loop (F12 prep plan / F14 interview focus / F13 resume advice) plus:

  * Gap -> plan contract (F12 consumes Phase 3 gaps, never re-judges them).
  * User isolation (every table bound to user_id).
  * Staleness: recomputing the match / reparsing the JD flags prepared content
    ``stale``; regenerating clears it.
  * User-edit protection: a manually edited task is not overwritten on
    regenerate.
  * AI-failure fallback: F12/F14/F13 still produce program-determinable output.
  * Empty states (no target / no match) and refresh-restore.

Hard contract (same as Phase 3): AI never writes a number (score / progress /
priority are program-owned).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.ai.gateway import AIGatewayError


def _auth_header(client, email=None, password="secret123"):
    if email is None:
        import uuid
        email = f"prep-{uuid.uuid4().hex[:8]}@test.com"
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


def _create_parse_confirm_match(client, h, raw=SAMPLE_JD):
    """Full Phase 3 setup: target job -> parse -> confirm -> match. Returns tj_id."""
    c = client.post("/api/target-job/create", json={"raw_jd": raw}, headers=h).json()
    tj_id = c["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj_id, "raw_jd": raw, "job_title": "产品经理", "company": "某某科技"},
        headers=h,
    ).json()
    am = p["target_job"]["ability_model"]
    client.put(
        f"/api/target-job/{tj_id}",
        json={"ability_model": am, "job_title": "产品经理", "company": "某某科技",
              "industry": am.get("industry", ""), "responsibilities": am.get("responsibilities", [])},
        headers=h,
    )
    m = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert m.status_code == 200
    return tj_id


# ----------------------------- F12: preparation plan -----------------------------
def test_f12_generate_plan_from_gaps(client):
    """F12 consumes Phase 3 gaps and produces one task per gap; no re-judgement."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)

    # number of gaps from the match
    gaps = client.get(f"/api/target-job/{tj_id}/match", headers=h).json()["gaps"]
    gap_abilities = {g["ability"] for g in gaps}

    r = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["ai_status"] in ("ok", "fallback")
    tasks = body["tasks"]
    assert len(tasks) == len(gap_abilities)
    assert {t["ability"] for t in tasks} == gap_abilities
    # program-owned fields present; AI never writes them
    for t in tasks:
        assert t["priority"] in ("high", "medium", "low")
        assert t["status"] == "pending"
        assert 0 <= t["order"]
        assert t["is_user_edited"] is False


def test_f12_plan_status_after_generate(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    body = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h).json()
    plan = body["prep_plan"]
    # all pending -> ready (not completed); progress 0
    assert plan["status"] == "ready"
    assert plan["overall_progress"] == 0.0


def test_f12_progress_completes_when_all_done(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    body = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h).json()
    task_ids = [t["task_id"] for t in body["tasks"]]
    for tid in task_ids:
        r = client.put(f"/api/prepare/task/{tid}", json={"status": "done"}, headers=h)
        assert r.status_code == 200
    plan = client.get("/api/prepare/home", headers=h).json()["prep_plan"]
    assert plan["status"] == "completed"
    assert plan["overall_progress"] == 100.0


# ----------------------------- F14: interview focus -----------------------------
def test_f14_interview_generate_and_read(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    r = client.post("/api/prepare/interview", json={"target_job_id": tj_id}, headers=h)
    assert r.status_code == 200
    items = r.json()["interview_focus"]
    assert len(items) >= 1
    for it in items:
        assert it["question"]
        assert it["evidence_status"] in ("sufficient", "insufficient", "none")
    # read back via GET
    r2 = client.get("/api/prepare/interview", params={"target_job_id": tj_id}, headers=h)
    assert r2.status_code == 200
    assert len(r2.json()["interview_focus"]) == len(items)


# ----------------------------- F13: resume advice -----------------------------
def test_f13_resume_generate_and_read(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    r = client.post("/api/prepare/resume", json={"target_job_id": tj_id}, headers=h)
    assert r.status_code == 200
    items = r.json()["resume_advice"]
    assert len(items) >= 1
    for it in items:
        assert it["advice_type"] in ("highlight", "evidence_gap", "keyword", "weak_link")
        assert it["content"]
    r2 = client.get("/api/prepare/resume", params={"target_job_id": tj_id}, headers=h)
    assert r2.status_code == 200
    assert len(r2.json()["resume_advice"]) == len(items)


# ----------------------------- user isolation -----------------------------
def test_isolation_prep_scoped_to_user(client):
    h1 = _auth_header(client, email="p1@test.com")
    h2 = _auth_header(client, email="p2@test.com")
    _build_profile(client, h1)
    _build_profile(client, h2)
    tj1 = _create_parse_confirm_match(client, h1)
    tj2 = _create_parse_confirm_match(client, h2)
    # user 1 generates a plan
    client.post("/api/prepare/generate", json={"target_job_id": tj1}, headers=h1)
    # user 2 home must show NO plan (their own, never generated)
    home2 = client.get("/api/prepare/home", params={"target_job_id": tj2}, headers=h2).json()
    assert home2["has_target"] is True
    assert home2["has_match"] is True
    assert home2["prep_plan"] is None
    # user 1 home shows the plan
    home1 = client.get("/api/prepare/home", params={"target_job_id": tj1}, headers=h1).json()
    assert home1["prep_plan"] is not None


# ----------------------------- staleness -----------------------------
class _AllMissingGateway:
    """Fake gateway that marks every ability 'missing' (score 0) on re-match."""

    def run(self, task, payload):
        if task == "f10_match_judge":
            abilities = payload["ability_model"]["abilities"]
            judgements = [
                {"ability": a["name"], "relation": "missing", "reason": "forced", "evidence": ""}
                for a in abilities
            ]
            return SimpleNamespace(status="ok", data={"judgements": judgements})
        if task == "f11_gap_explain":
            return SimpleNamespace(status="ok", data={"why": "w", "evidence": "e", "improvement_direction": "d"})
        return SimpleNamespace(status="ok", data={})


def test_stale_after_rematch_then_cleared_on_regenerate(client, monkeypatch):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)

    # generate -> not stale
    client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    client.post("/api/prepare/interview", json={"target_job_id": tj_id}, headers=h)
    client.post("/api/prepare/resume", json={"target_job_id": tj_id}, headers=h)
    home = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home["prep_stale"] is False
    assert home["interview_stale"] is False
    assert home["resume_stale"] is False

    # re-match with a different signature (all missing) -> stale
    monkeypatch.setattr("app.services.match_service.get_gateway", lambda: _AllMissingGateway())
    rm = client.post(f"/api/target-job/{tj_id}/match", json={}, headers=h)
    assert rm.status_code == 200

    home2 = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home2["prep_stale"] is True
    assert home2["interview_stale"] is True
    assert home2["resume_stale"] is True

    # regenerate plan -> snapshot refreshed -> stale cleared
    client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    home3 = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home3["prep_stale"] is False
    assert home3["interview_stale"] is True  # interview not regenerated yet
    # regenerate interview + resume -> all clear
    client.post("/api/prepare/interview", json={"target_job_id": tj_id}, headers=h)
    client.post("/api/prepare/resume", json={"target_job_id": tj_id}, headers=h)
    home4 = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home4["interview_stale"] is False
    assert home4["resume_stale"] is False


# ----------------------------- user-edit protection -----------------------------
def test_user_edit_protected_on_regenerate(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    body = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h).json()
    task = body["tasks"][0]
    tid = task["task_id"]
    original_title = task["title"]

    # user edits the task (title + done + note)
    edited = client.put(
        f"/api/prepare/task/{tid}",
        json={"title": "用户自定义标题", "status": "done", "user_note": "我的备注"},
        headers=h,
    ).json()["task"]
    assert edited["is_user_edited"] is True
    assert edited["status"] == "done"

    # regenerate the plan
    body2 = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h).json()
    regenerated = next(t for t in body2["tasks"] if t["task_id"] == tid)
    # human fields are preserved, not overwritten by AI
    assert regenerated["title"] == "用户自定义标题"
    assert regenerated["status"] == "done"
    assert regenerated["user_note"] == "我的备注"
    assert regenerated["is_user_edited"] is True
    # a never-edited task keeps its (possibly refreshed) AI/title or default
    other = [t for t in body2["tasks"] if t["task_id"] != tid]
    if other:
        assert other[0]["is_user_edited"] is False


# ----------------------------- AI fallback -----------------------------
def test_f12_ai_failure_fallback(client, monkeypatch):
    """Force the gateway to raise; F12 must still produce tasks (default titles)."""
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)

    class _BoomGateway:
        def run(self, *a, **k):
            raise AIGatewayError("forced")

    monkeypatch.setattr("app.services.prep_service.get_gateway", lambda: _BoomGateway())
    r = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["ai_status"] == "fallback"
    gaps = client.get(f"/api/target-job/{tj_id}/match", headers=h).json()["gaps"]
    # one task per gap, even with no AI
    assert len(body["tasks"]) == len(gaps)


def test_interview_resume_ai_failure_fallback(client, monkeypatch):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)

    class _BoomGateway:
        def run(self, *a, **k):
            raise AIGatewayError("forced")

    monkeypatch.setattr("app.services.prep_service.get_gateway", lambda: _BoomGateway())
    ri = client.post("/api/prepare/interview", json={"target_job_id": tj_id}, headers=h)
    rr = client.post("/api/prepare/resume", json={"target_job_id": tj_id}, headers=h)
    assert ri.status_code == 200 and ri.json()["ai_status"] == "fallback"
    assert rr.status_code == 200 and rr.json()["ai_status"] == "fallback"


# ----------------------------- empty states -----------------------------
def test_empty_state_no_target(client):
    h = _auth_header(client)
    r = client.get("/api/prepare/home", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["has_target"] is False
    assert body["prep_plan"] is None


def test_empty_state_no_match_blocks_generate(client):
    h = _auth_header(client)
    # target exists (parsed + confirmed) but no match yet
    c = client.post("/api/target-job/create", json={"raw_jd": SAMPLE_JD}, headers=h).json()
    tj_id = c["target_job_id"]
    p = client.post(
        "/api/target-job/parse",
        json={"target_job_id": tj_id, "raw_jd": SAMPLE_JD, "job_title": "产品经理", "company": "某某科技"},
        headers=h,
    ).json()
    am = p["target_job"]["ability_model"]
    client.put(f"/api/target-job/{tj_id}", json={"ability_model": am}, headers=h)

    home = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home["has_target"] is True
    assert home["has_match"] is False

    # generate requires a match -> 422 (no_match)
    r = client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "no_match"


# ----------------------------- refresh restore -----------------------------
def test_refresh_restore_state(client):
    h = _auth_header(client)
    _build_profile(client, h)
    tj_id = _create_parse_confirm_match(client, h)
    client.post("/api/prepare/generate", json={"target_job_id": tj_id}, headers=h)
    client.post("/api/prepare/interview", json={"target_job_id": tj_id}, headers=h)
    client.post("/api/prepare/resume", json={"target_job_id": tj_id}, headers=h)

    # simulate refresh: re-fetch home, everything persisted
    home = client.get("/api/prepare/home", params={"target_job_id": tj_id}, headers=h).json()
    assert home["prep_plan"] is not None
    assert len(home["tasks"]) >= 1
    assert len(home["interview_focus"]) >= 1
    assert len(home["resume_advice"]) >= 1
    assert home["prep_stale"] is False
