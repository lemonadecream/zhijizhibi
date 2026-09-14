"""Phase 6 Offer workspace tests (F17-F24).

Covers: offer CRUD, salary after-tax (F19), city cost (F20), weights (F22),
composite (F23), AI analysis (F21/F24) under mock provider, and user isolation.
"""
import pytest
from fastapi.testclient import TestClient


def _auth_header(client):
    r = client.post("/api/auth/register", json={
        "email": "offeruser@example.com", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json().get('access_token', '')}"}


def _make_offer(client, h, **over):
    payload = {
        "company": "字节跳动", "job_title": "后端开发", "city": "北京",
        "salary": {"monthly_base": 25000, "annual_bonus_months": 3},
        "special_deduction": 2000,
    }
    payload.update(over)
    return client.post("/api/offer/applications", json=payload, headers=h).json()


def test_offer_crud_and_isolation(client):
    h = _auth_header(client)
    o = _make_offer(client, h)
    assert o["company"] == "字节跳动"
    assert o["status"] == "draft"
    assert o["status_label"] == "草稿"

    # list
    lst = client.get("/api/offer/applications", headers=h).json()
    assert lst["total"] == 1

    # update
    upd = client.put(f"/api/offer/applications/{o['offer_id']}",
                     json={"status": "active"}, headers=h).json()
    assert upd["status"] == "active"

    # delete
    client.delete(f"/api/offer/applications/{o['offer_id']}", headers=h)
    lst = client.get("/api/offer/applications", headers=h).json()
    assert lst["total"] == 0


def test_salary_after_tax_f19(client):
    h = _auth_header(client)
    o = _make_offer(client, h)
    r = client.post(f"/api/offer/applications/{o['offer_id']}/salary_calc", json={}, headers=h).json()
    res = r["results"]
    # Beijing monthly_base 25000, fund_rate 0.12 default
    assert res["monthly_base"] == 25000
    # insurance total positive
    assert res["insurance_total"] > 0
    # after-tax monthly strictly less than gross
    assert res["monthly_after_tax"] < 25000
    assert res["annual_after_tax"] > 0
    # sign_on/equity excluded from core
    assert "sign_on" in res


def test_city_cost_override_f20(client):
    h = _auth_header(client)
    cities = client.get("/api/offer/cities", headers=h).json()
    assert any(c["city"] == "北京" for c in cities["cities"])
    # override
    upd = client.put("/api/offer/cities/北京", json={"rent": 4000}, headers=h).json()
    assert upd["rent"] == 4000
    cities = client.get("/api/offer/cities", headers=h).json()
    ov = [c for c in cities["user_overrides"] if c["city"] == "北京"][0]
    assert ov["rent"] == 4000


def test_weights_f22(client):
    h = _auth_header(client)
    w = client.put("/api/offer/weights", json={"weights": {"economic": 40, "disposable": 30,
                                                           "workload": 10, "stability": 5, "growth": 10, "match": 5},
                                             "preset_name": "salary"}, headers=h).json()
    assert w["preset_name"] == "salary"
    got = client.get("/api/offer/weights", headers=h).json()
    assert got["weights"]["economic"] == 40


def test_comparison_f23_and_f24(client):
    h = _auth_header(client)
    o1 = _make_offer(client, h, company="A", salary={"monthly_base": 30000, "annual_bonus_months": 3})
    o2 = (_make_offer(client, h, company="B", city="成都",
                      salary={"monthly_base": 22000, "annual_bonus_months": 2}))
    # mark active
    client.put(f"/api/offer/applications/{o1['offer_id']}", json={"status": "active"}, headers=h)
    client.put(f"/api/offer/applications/{o2['offer_id']}", json={"status": "active"}, headers=h)
    comp = client.get("/api/offer/comparison", headers=h).json()
    assert comp["comparison_id"]
    offers = comp["offers"]
    assert len(offers) == 2
    scores = [o["composite_score"] for o in offers]
    assert all(isinstance(s, (int, float)) for s in scores)
    # ranks assigned
    assert {o["rank"] for o in offers} == {1, 2}
    # F24 analysis present (mock)
    assert "recommendations" in comp["analysis"]


def test_offer_accept_keeps_others(client):
    h = _auth_header(client)
    o1 = _make_offer(client, h)
    o2 = _make_offer(client, h, company="C")
    client.put(f"/api/offer/applications/{o1['offer_id']}", json={"status": "active"}, headers=h)
    client.put(f"/api/offer/applications/{o2['offer_id']}", json={"status": "active"}, headers=h)
    acc = client.post(f"/api/offer/applications/{o1['offer_id']}/accept", headers=h).json()
    assert acc["status"] == "accepted"
    assert len(acc["other_active_offers"]) == 1  # o2 kept as-is, NOT auto-rejected
    o2b = client.get(f"/api/offer/applications/{o2['offer_id']}", headers=h).json()
    assert o2b["status"] == "active"


def test_user_isolation(client):
    import time
    h1 = _auth_header(client)
    o = _make_offer(client, h1)
    r2 = client.post("/api/auth/register", json={
        "email": f"other_{int(time.time())}@e.com", "password": "secret123"})
    h2 = {"Authorization": f"Bearer {r2.json().get('access_token', '')}"}
    # user 2 cannot see user 1's offer
    got = client.get(f"/api/offer/applications/{o['offer_id']}", headers=h2)
    assert got.status_code == 404
