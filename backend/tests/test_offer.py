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


def _confirm_scores(offer_id: int, scores: dict) -> None:
    """写入"用户确认的四维 0-100 分"（offer_dimension）。

    Demo seed 走的是同一个服务函数。AI 永远不会写这张表——它只写
    ai_dimension_reference 的档位；数字必须由用户/匹配产生。
    """
    from app.db.base import SessionLocal
    from app.models.offer import Offer
    from app.services.decision_service import save_dimension_scores

    with SessionLocal() as db:
        row = db.get(Offer, offer_id)
        assert row is not None
        save_dimension_scores(db, user_id=row.user_id, offer_id=offer_id, scores=scores)


def test_comparison_scores_nonzero_and_ordered(client):
    """三个 Offer 补齐四维分 + 税后薪资后，综合分必须非 0 且排序稳定。

    回归背景（本用例守的就是这个）：``offer_dimension`` 当时没有任何可达写入路径，
    且 ``compute_comparison`` 从不注入 ``economic`` / ``disposable``，
    结果是**所有用户**的综合分恒为 0，排名退化成插入顺序（显示 1/2/3 名却全是 0 分）。
    """
    h = _auth_header(client)
    # 与 Demo seed 同构的三份 Offer：成长 vs 稳定的真实取舍
    specs = [
        ("云枢科技", "杭州", 13000, {"growth": 82, "match": 78, "workload": 65, "stability": 80}),
        ("麦浪文化", "上海", 15000, {"growth": 90, "match": 88, "workload": 40, "stability": 55}),
        ("星野数据", "杭州", 11000, {"growth": 62, "match": 70, "workload": 82, "stability": 85}),
    ]
    for company, city, base, dims in specs:
        o = _make_offer(client, h, company=company, city=city,
                        salary={"monthly_base": base, "annual_bonus_months": 3})
        oid = o["offer_id"]
        client.put(f"/api/offer/applications/{oid}", json={"status": "active"}, headers=h)
        client.post(f"/api/offer/applications/{oid}/salary_calc", json={}, headers=h)
        _confirm_scores(oid, dims)

    client.put("/api/offer/weights",
               json={"weights": {"economic": 15, "disposable": 10, "workload": 10,
                                 "stability": 10, "growth": 40, "match": 15},
                     "preset_name": "growth"}, headers=h)

    offers = client.get("/api/offer/comparison", headers=h).json()["offers"]
    assert len(offers) == 3

    scores = [o["composite_score"] for o in offers]
    # 1) 综合分非 0
    assert all(s > 0 for s in scores), f"composite 不应为 0: {scores}"
    # 2) 降序稳定 + rank 一致
    assert scores == sorted(scores, reverse=True), scores
    assert [o["rank"] for o in offers] == [1, 2, 3]
    # 3) 六个维度全部参与计算（没有静默跳过的权重）
    for o in offers:
        for dim in ("economic", "disposable", "workload", "stability", "growth", "match"):
            assert o["dimension_scores"][dim] is not None, (o["company"], dim)
    # 4) 该数据集下"高成长"应胜出、"稳定但成长低"垫底——锁住排序语义
    assert [o["company"] for o in offers] == ["麦浪文化", "云枢科技", "星野数据"]


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


def test_offer_routes_release_db_sessions(client):
    """Offer 路由必须从 ``Depends(get_db)`` 取 session，请求结束即把连接还给池。

    回归背景（本用例守的就是这个）：
    ``app/api/offer.py`` 曾经是**全项目唯一**不用 ``Depends(get_db)`` 的路由 ——
    它自带一个 ``_db()``，直接 ``return SessionLocal()`` 且从不 close
    （只有 ``salary_calc`` 用 try/finally 关掉了）。每个请求因此漏一个池化连接，
    默认池只有 size 5 + overflow 10，请求量一上来就
    ``QueuePool limit of size 5 overflow 10 reached``（30s 超时）。

    现在全部端点改用项目标准的 ``get_db``（yield 出 session，finally 里 close），
    所以每打完一个端点，池里的 checked-out 连接数都必须回到基线；
    连跑多轮也不能出现线性增长。

    同时顺带断言每个端点都返回 2xx —— 否则「连接还回来了」可能只是因为它
    压根没跑成（get_db 在异常路径上同样会 close），测试就变成空转。
    """
    from app.db.base import engine

    pool = engine.pool
    assert hasattr(pool, "checkedout"), f"连接池不可观测: {type(pool).__name__}"

    h = _auth_header(client)
    o = _make_offer(client, h)
    oid = o["offer_id"]
    client.put(f"/api/offer/applications/{oid}", json={"status": "active"}, headers=h)

    # 删除 / accept 会把 Offer 推出可比较状态，各用一个临时 Offer 来打
    def fresh_offer_id() -> int:
        return client.post("/api/offer/applications", json={
            "company": "临时", "job_title": "临时", "city": "北京"}, headers=h).json()["offer_id"]

    def delete_fresh():
        return client.delete(f"/api/offer/applications/{fresh_offer_id()}", headers=h)

    def accept_fresh():
        return client.post(f"/api/offer/applications/{fresh_offer_id()}/accept", headers=h)

    # offer.py 里全部 13 个端点，一个都不漏
    endpoints: list[tuple[str, object]] = [
        ("POST /applications", lambda: client.post("/api/offer/applications", json={
            "company": "临时", "job_title": "临时", "city": "北京"}, headers=h)),
        ("GET /applications", lambda: client.get("/api/offer/applications", headers=h)),
        ("GET /applications/{id}", lambda: client.get(f"/api/offer/applications/{oid}", headers=h)),
        ("PUT /applications/{id}",
         lambda: client.put(f"/api/offer/applications/{oid}", json={"note": "备注"}, headers=h)),
        ("POST /applications/{id}/salary_calc",
         lambda: client.post(f"/api/offer/applications/{oid}/salary_calc", json={}, headers=h)),
        ("POST /applications/{id}/assess",
         lambda: client.post(f"/api/offer/applications/{oid}/assess", json={}, headers=h)),
        ("DELETE /applications/{id}", delete_fresh),
        ("POST /applications/{id}/accept", accept_fresh),
        ("GET /cities", lambda: client.get("/api/offer/cities", headers=h)),
        ("PUT /cities/{city}",
         lambda: client.put("/api/offer/cities/北京", json={"rent": 3200}, headers=h)),
        ("GET /weights", lambda: client.get("/api/offer/weights", headers=h)),
        ("PUT /weights", lambda: client.put("/api/offer/weights", json={
            "weights": {"economic": 25, "disposable": 20, "workload": 15,
                        "stability": 15, "growth": 15, "match": 10},
            "preset_name": "balanced"}, headers=h)),
        ("GET /comparison", lambda: client.get("/api/offer/comparison", headers=h)),
    ]

    baseline = pool.checkedout()

    # ① 逐个端点核对：一旦有端点漏连接，立刻带着端点名失败（而不是等到池耗尽）
    for label, call in endpoints:
        resp = call()
        assert 200 <= resp.status_code < 300, f"{label} 返回 {resp.status_code}: {resp.text[:200]}"
        now = pool.checkedout()
        assert now <= baseline, (
            f"{label} 结束后连接没有还回连接池：baseline={baseline}, now={now} "
            f"—— 这个端点仍在自行创建 Session 而没有 close"
        )

    # ② 全部端点再连跑两轮：真正的泄漏会随请求线性增长，修好后必须保持平坦
    for _ in range(2):
        for _, call in endpoints:
            call()
    assert pool.checkedout() <= baseline, (
        f"连接数随请求增长：baseline={baseline}, now={pool.checkedout()}"
    )
