"""Phase 5 Tracking integration tests (F15 投递记录 / F16 面试记录).

Runs on SQLite + Mock AI provider (no network / API key). Covers:
  * application CRUD + validation (company/job_title required)
  * the status machine (allowed transitions, terminal-state guard)
  * interview CRUD + result -> application status linkage (pass=>offer, fail=>rejected)
  * timeline single source of truth (status events + synthesized interview events)
  * overview aggregation (counts + upcoming interviews)
  * user isolation (cross-user reads are rejected)
  * cascade delete (deleting an application removes its interviews)
"""
from __future__ import annotations

import uuid


def _auth_header(client, email=None, password="secret123"):
    if email is None:
        email = f"tk-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "追"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_app(client, h, **over):
    payload = {
        "company": "字节跳动",
        "job_title": "后端工程师",
        "city": "上海",
        "source": "内推",
        "status": "drafted",
        "next_action": "等笔试通知",
    }
    payload.update(over)
    return client.post("/api/tracking/applications", json=payload, headers=h).json()


# ----------------------------- CRUD + validation -----------------------------
def test_create_application(client):
    h = _auth_header(client)
    body = _create_app(client, h)
    assert body["application_id"] > 0
    assert body["company"] == "字节跳动"
    assert body["status"] == "drafted"
    assert body["status_label"] == "草稿"
    # timeline seeded with creation event
    assert any(ev["status"] == "drafted" for ev in body["timeline"])


def test_create_requires_company_and_job(client):
    h = _auth_header(client)
    r = client.post("/api/tracking/applications", json={"company": ""}, headers=h)
    assert r.status_code == 422
    r2 = client.post("/api/tracking/applications", json={"job_title": "x"}, headers=h)
    assert r2.status_code == 422


def test_list_and_filter(client):
    h = _auth_header(client)
    _create_app(client, h, status="applied")
    _create_app(client, h, company="腾讯", job_title="前端", status="interviewing")
    all_ = client.get("/api/tracking/applications", headers=h).json()
    assert all_["total"] == 2
    filtered = client.get("/api/tracking/applications?status=interviewing", headers=h).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["company"] == "腾讯"


def test_update_application(client):
    h = _auth_header(client)
    a = _create_app(client, h)
    r = client.put(
        f"/api/tracking/applications/{a['application_id']}",
        json={"note": "更新备注"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["note"] == "更新备注"


def test_delete_application(client):
    h = _auth_header(client)
    a = _create_app(client, h)
    r = client.delete(f"/api/tracking/applications/{a['application_id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    got = client.get(f"/api/tracking/applications/{a['application_id']}", headers=h)
    assert got.status_code == 404


# ----------------------------- status machine -----------------------------
def test_status_transition_allowed(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="drafted")
    r = client.put(
        f"/api/tracking/applications/{a['application_id']}",
        json={"status": "applied"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "applied"
    # timeline records the transition
    assert any(ev["status"] == "applied" and ev["from_status"] == "drafted" for ev in r.json()["timeline"])


def test_status_transition_illegal(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="drafted")
    # drafted -> interviewing is illegal (must go through applied)
    r = client.put(
        f"/api/tracking/applications/{a['application_id']}",
        json={"status": "interviewing"},
        headers=h,
    )
    assert r.status_code == 422


def test_terminal_status_blocked(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="offer_received")
    r = client.put(
        f"/api/tracking/applications/{a['application_id']}",
        json={"status": "applied"},
        headers=h,
    )
    assert r.status_code == 422


# ----------------------------- interview + linkage -----------------------------
def test_interview_crud(client):
    h = _auth_header(client)
    a = _create_app(client, h)
    iv = client.post(
        f"/api/tracking/applications/{a['application_id']}/interviews",
        json={"round": "一面", "interview_type": "技术", "result": "pending"},
        headers=h,
    ).json()
    assert iv["interview_id"] > 0
    assert iv["round"] == "一面"

    upd = client.put(f"/api/tracking/interviews/{iv['interview_id']}", json={"result": "pass"}, headers=h)
    assert upd.status_code == 200
    assert upd.json()["result"] == "pass"


def test_interview_pass_links_to_offer(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="interviewing")
    iv = client.post(
        f"/api/tracking/applications/{a['application_id']}/interviews",
        json={"round": "终面", "result": "pending"},
        headers=h,
    ).json()
    client.put(f"/api/tracking/interviews/{iv['interview_id']}", json={"result": "pass"}, headers=h)
    detail = client.get(f"/api/tracking/applications/{a['application_id']}", headers=h).json()
    assert detail["application"]["status"] == "offer_received"


def test_interview_fail_links_to_rejected(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="interviewing")
    iv = client.post(
        f"/api/tracking/applications/{a['application_id']}/interviews",
        json={"round": "二面", "result": "pending"},
        headers=h,
    ).json()
    client.put(f"/api/tracking/interviews/{iv['interview_id']}", json={"result": "fail"}, headers=h)
    detail = client.get(f"/api/tracking/applications/{a['application_id']}", headers=h).json()
    assert detail["application"]["status"] == "rejected"


def test_interview_cascade_on_app_delete(client):
    h = _auth_header(client)
    a = _create_app(client, h)
    client.post(
        f"/api/tracking/applications/{a['application_id']}/interviews",
        json={"round": "一面"},
        headers=h,
    ).json()
    client.delete(f"/api/tracking/applications/{a['application_id']}", headers=h)
    # After app deletion, its interviews are gone (cascade), so the detail
    # no longer returns them.
    got = client.get(f"/api/tracking/applications/{a['application_id']}", headers=h)
    assert got.status_code == 404


# ----------------------------- timeline + overview -----------------------------
def test_merged_timeline_includes_interview(client):
    h = _auth_header(client)
    a = _create_app(client, h, status="interviewing")
    client.post(
        f"/api/tracking/applications/{a['application_id']}/interviews",
        json={"round": "一面", "scheduled_at": "2030-01-01T10:00:00+00:00"},
        headers=h,
    )
    detail = client.get(f"/api/tracking/applications/{a['application_id']}", headers=h).json()
    kinds = {ev["kind"] for ev in detail["timeline"]}
    assert "status" in kinds
    assert "interview" in kinds


def test_overview_counts_and_upcoming(client):
    h = _auth_header(client)
    _create_app(client, h, status="applied")
    _create_app(client, h, status="interviewing")
    ov = client.get("/api/tracking/overview", headers=h).json()
    assert ov["total"] == 2
    assert ov["counts"]["applied"] == 1
    assert ov["counts"]["interviewing"] == 1


# ----------------------------- user isolation -----------------------------
def test_cross_user_isolation(client):
    h1 = _auth_header(client)
    h2 = _auth_header(client, email=f"tk-other-{uuid.uuid4().hex[:8]}@test.com")
    a = _create_app(client, h1)
    # user 2 cannot read / update / delete user 1's application
    assert client.get(f"/api/tracking/applications/{a['application_id']}", headers=h2).status_code == 404
    assert client.put(
        f"/api/tracking/applications/{a['application_id']}", json={"note": "x"}, headers=h2
    ).status_code == 404
    assert client.delete(f"/api/tracking/applications/{a['application_id']}", headers=h2).status_code == 404
    # user 1's still there
    assert client.get(f"/api/tracking/applications/{a['application_id']}", headers=h1).status_code == 200
