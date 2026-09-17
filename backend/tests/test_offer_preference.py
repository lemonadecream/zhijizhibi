"""决策偏好（F22 权重）→ 综合分（F23）链路回归。

背景（线上验收发现的产品问题）：
Offer 页写着「调整你的决策偏好（影响综合排序，但不替你做决定）」，
但改了偏好之后卡片上的综合得分一动不动 —— UI 承诺和实际计算链路没有闭合。

排查结论：后端链路本身是通的（``PUT /api/offer/weights`` 落 decision_weight，
``GET /api/offer/comparison`` 经过 ``compute_comparison`` → ``get_weights``
读到这份权重，再交给 ``_finalize_comparison`` 加权）。断点在**前端**：
拉分数的 useEffect 依赖数组里只有 offers，权重保存后不会重新拉取。
本文件的作用是给这条链路钉住后端一侧的行为契约，让"重新拉取一定能拿到新分数"
成为可验证的前提，而不是假设。

产品约束（本文件全部围绕它们设计）：
  * 六个维度不变；四维用户确认分来自用户/匹配数据，不因偏好而变；
  * economic / disposable 仍由程序从税后收入 + 城市成本算出；
  * 综合分 = 程序归一化 + 加权，AI 不产生任何数字；
  * 不新增评分维度，不把 AI 的档位映射成数字。
"""
import pytest

from app.ai.gateway import AIResult
from app.services import analysis_service


# 与 Demo seed 同构的三份 Offer（公司 / 城市 / 月薪 / 年终月数 / 已确认的四维分）。
# 用同一份数据是为了让这里钉住的分数与用户在线上看到的是同一套。
DEMO_OFFERS = [
    ("云枢科技", "杭州", 13000, 3, {"growth": 82, "match": 78, "workload": 65, "stability": 80}),
    ("麦浪文化", "上海", 15000, 2, {"growth": 90, "match": 88, "workload": 40, "stability": 55}),
    ("星野数据", "杭州", 11000, 4, {"growth": 62, "match": 70, "workload": 82, "stability": 85}),
]

# 与 decision_service.PRESETS 一致（相对权重，无需归一化）
PRESET = {
    "balanced": {"economic": 25, "disposable": 20, "workload": 15, "stability": 15, "growth": 15, "match": 10},
    "salary": {"economic": 40, "disposable": 30, "workload": 10, "stability": 5, "growth": 10, "match": 5},
    "stability": {"economic": 15, "disposable": 10, "workload": 15, "stability": 35, "growth": 15, "match": 10},
    "growth": {"economic": 15, "disposable": 10, "workload": 10, "stability": 10, "growth": 40, "match": 15},
}

ALL_DIMS = ("economic", "disposable", "workload", "stability", "growth", "match")

# Case A 钉住的确定值：Demo 默认偏好 = growth（seed_demo.DECISION_WEIGHTS）。
# 这里必须写死数字而不是"算一遍再比" —— 否则阈值一变，测试会跟着一起漂，
# 就失去"回归"的意义了。
GROWTH_EXPECTED = {
    "麦浪文化": (83.70, 1),
    "云枢科技": (82.13, 2),
    "星野数据": (72.60, 3),
}
# 同一份数据、只换偏好（成长优先 → 稳定优先）后的确定值。
# 注意排名发生了**实质性反转**：麦浪文化从第 1 掉到第 3。
STABILITY_EXPECTED = {
    "云枢科技": (80.98, 1),
    "星野数据": (78.95, 2),
    "麦浪文化": (72.55, 3),
}
SALARY_EXPECTED = {
    "麦浪文化": (90.15, 1),
    "云枢科技": (87.52, 2),
    "星野数据": (79.88, 3),
}


def _auth_header(client):
    r = client.post("/api/auth/register", json={
        "email": "pref@example.com", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json().get('access_token', '')}"}


def _save_weights(client, h, name: str):
    return client.put("/api/offer/weights",
                      json={"weights": PRESET[name], "preset_name": name}, headers=h)


def _build_offer(client, h, *, company: str, city: str, base: int, bonus: int,
                 dims: dict) -> int:
    """建一份 Offer：创建 → 激活 → 税后计算 → 写入"用户已确认的四维分"。

    最后一步不能省：``offer_dimension`` 只存四个定性分，
    缺了它 ``_finalize_comparison`` 会把 75% 的权重静默跳过。
    """
    from app.db.base import SessionLocal
    from app.models.offer import Offer
    from app.services.decision_service import save_dimension_scores

    created = client.post("/api/offer/applications", json={
        "company": company, "job_title": "产品运营", "city": city,
        "salary": {"monthly_base": base, "annual_bonus_months": bonus},
        "special_deduction": 1500,
    }, headers=h).json()
    oid = created["offer_id"]
    client.put(f"/api/offer/applications/{oid}", json={"status": "active"}, headers=h)
    client.post(f"/api/offer/applications/{oid}/salary_calc", json={}, headers=h)
    with SessionLocal() as db:
        row = db.get(Offer, oid)
        assert row is not None
        save_dimension_scores(db, user_id=row.user_id, offer_id=oid, scores=dims)
    return oid


def _build_demo_offers(client, h) -> list[int]:
    return [
        _build_offer(client, h, company=company, city=city, base=base, bonus=bonus, dims=dims)
        for company, city, base, bonus, dims in DEMO_OFFERS
    ]


def _comparison(client, h) -> list[dict]:
    return client.get("/api/offer/comparison", headers=h).json()["offers"]


def _by_company(offers: list[dict]) -> dict:
    return {o["company"]: o for o in offers}


def _recompute(dim_scores: dict, weights: dict) -> float:
    """用测试自己的代码把综合分算回去：Σ(score×w) / Σ(active_w)。

    这就是"综合分由程序确定性计算"的可验证含义 —— 只要页面上那个数字
    与这条公式对得上，它就不可能是 AI 写的。缺失维度不参与分母。
    """
    num = den = 0.0
    for dim in ALL_DIMS:
        s = dim_scores.get(dim)
        w = weights.get(dim, 0) or 0
        if s is not None and w > 0:
            num += s * w
            den += w
    return round(num / den, 2) if den > 0 else 0.0


# --------------------------------------------------------------------------
# Case A：Demo 默认偏好（成长优先）下的确定分数与排序
# --------------------------------------------------------------------------
def test_case_a_demo_default_preference_is_deterministic(client):
    h = _auth_header(client)
    _build_demo_offers(client, h)
    _save_weights(client, h, "growth")

    offers = _comparison(client, h)
    got = _by_company(offers)
    assert set(got) == set(GROWTH_EXPECTED)

    for company, (score, rank) in GROWTH_EXPECTED.items():
        assert got[company]["composite_score"] == score, (company, got[company]["composite_score"])
        assert got[company]["rank"] == rank, (company, got[company]["rank"])

    # 排序即分数降序（rank 与 composite 必须自洽）
    scores = [o["composite_score"] for o in offers]
    assert scores == sorted(scores, reverse=True)

    # 六维全部参与，且两个量化维度确实由程序给出（非 None）
    for o in offers:
        for dim in ALL_DIMS:
            assert o["dimension_scores"][dim] is not None, (o["company"], dim)


# --------------------------------------------------------------------------
# Case B：换一个明显不同的偏好 → 分数必须变，排序依据也必须跟着变
# --------------------------------------------------------------------------
def test_case_b_changing_preference_changes_scores_and_order(client):
    h = _auth_header(client)
    _build_demo_offers(client, h)

    _save_weights(client, h, "growth")
    before = _by_company(_comparison(client, h))

    # 成长优先 → 稳定优先：权重意义上完全不同的一种价值观
    _save_weights(client, h, "stability")
    after = _by_company(_comparison(client, h))

    # ① 至少一个 Offer 的综合分必须真的变了
    changed = [c for c in before if before[c]["composite_score"] != after[c]["composite_score"]]
    assert changed, "换了偏好综合分却一个都没变 —— 偏好没有进入计算"

    # ② 偏好变化足以改变排序依据时，排序也必须跟着变（这里第 1 名发生反转）
    assert before["麦浪文化"]["rank"] == 1
    assert after["云枢科技"]["rank"] == 1
    assert after["麦浪文化"]["rank"] == 3
    assert [o["company"] for o in _comparison(client, h)] != \
           sorted(before, key=lambda c: before[c]["rank"])

    # ③ 钉住确定值
    for company, (score, rank) in STABILITY_EXPECTED.items():
        assert after[company]["composite_score"] == score, (company, after[company]["composite_score"])
        assert after[company]["rank"] == rank

    # ④ 换回"薪资优先"是另一种变化（分数全部抬升，但仍遵循同一套公式）
    _save_weights(client, h, "salary")
    salary = _by_company(_comparison(client, h))
    for company, (score, rank) in SALARY_EXPECTED.items():
        assert salary[company]["composite_score"] == score, (company, salary[company]["composite_score"])
        assert salary[company]["rank"] == rank

    # ⑤ 变的只能是"权重"，四维用户确认分与两个量化分必须逐位不变
    for company in before:
        assert before[company]["dimension_scores"] == salary[company]["dimension_scores"], company


def test_case_b2_composite_is_recomputable_from_weights(client):
    """综合分是 program 的纯函数：用返回的维度分 + 自己存的权重能精确算回去。

    这条断言同时挡住两件事：
      * AI 写数字（AI 写的值不会与公式吻合）；
      * 偏好被"部分"应用（权重对不上，公式就配不平）。
    """
    h = _auth_header(client)
    _build_demo_offers(client, h)

    for preset in ("growth", "salary", "stability", "balanced"):
        _save_weights(client, h, preset)
        payload = client.get("/api/offer/comparison", headers=h).json()

        # 服务端回显的权重必须就是我们刚才存的那份
        assert payload["weights"] == PRESET[preset], preset
        assert payload["weight_snapshot"] == PRESET[preset], preset

        for o in payload["offers"]:
            expected = _recompute(o["dimension_scores"], PRESET[preset])
            assert o["composite_score"] == expected, (preset, o["company"])


# --------------------------------------------------------------------------
# Case C：同一偏好重复计算 → 结果必须稳定、确定
# --------------------------------------------------------------------------
def test_case_c_repeated_computation_is_stable(client):
    h = _auth_header(client)
    _build_demo_offers(client, h)
    _save_weights(client, h, "growth")

    runs = [_comparison(client, h) for _ in range(3)]
    fingerprints = [
        [(o["company"], o["composite_score"], o["rank"]) for o in run]
        for run in runs
    ]
    assert fingerprints[0] == fingerprints[1] == fingerprints[2]

    # 定量维度来自"相对归一化"（最高值映射 100），重复跑不应漂移
    for run in runs[1:]:
        assert run == runs[0]


def test_case_c2_preference_is_isolated_per_user(client):
    """偏好是按 user 存的：A 换了偏好不能影响 B 的分数。

    两个用户各铺满三份 Demo Offer（请求数不小）—— 这正是它当初的价值：
    在 Offer 路由还漏连接时，这个体量会直接撞到 QueuePool 超时。
    连接生命周期已改回项目标准的 Depends(get_db)，
    因此这里**刻意保持完整体量**，不再为回避问题而缩减请求数。
    """
    h1 = _auth_header(client)
    _build_demo_offers(client, h1)
    _save_weights(client, h1, "growth")
    a_before = _by_company(_comparison(client, h1))

    r2 = client.post("/api/auth/register", json={
        "email": "pref_other@example.com", "password": "secret123"})
    h2 = {"Authorization": f"Bearer {r2.json().get('access_token', '')}"}
    _build_demo_offers(client, h2)
    _save_weights(client, h2, "stability")

    # 偏好各存各的
    assert client.get("/api/offer/weights", headers=h1).json()["preset_name"] == "growth"
    assert client.get("/api/offer/weights", headers=h2).json()["preset_name"] == "stability"

    # B 的偏好没有污染 A 的分数
    a_after = _by_company(_comparison(client, h1))
    for company in a_before:
        assert a_before[company]["composite_score"] == a_after[company]["composite_score"]


# --------------------------------------------------------------------------
# 数字必须与 AI 无关：把 AI 打断，综合分必须一模一样
# --------------------------------------------------------------------------
class _DeadGateway:
    """模拟"AI 完全不可用"：F24 只剩确定性 fallback。"""

    def __init__(self):
        self.calls = 0

    def run(self, name, input_dict):
        self.calls += 1
        return AIResult(status="fallback", data={"recommendations": []},
                        error="ai offline", fallback_available=True)


def test_composite_scores_survive_ai_outage(client, monkeypatch):
    h = _auth_header(client)
    _build_demo_offers(client, h)
    _save_weights(client, h, "growth")

    healthy = _by_company(_comparison(client, h))

    dead = _DeadGateway()
    monkeypatch.setattr(analysis_service, "get_gateway", lambda: dead)
    degraded = client.get("/api/offer/comparison", headers=h).json()

    assert dead.calls >= 1, "F24 一次都没被调用，说明这条断言没有真的打断 AI"
    assert degraded["analysis"]["ai_status"] == "fallback"

    # ★ 核心断言：AI 挂了，综合分与排名逐位不变 → 数字不可能来自 AI
    broken = _by_company(degraded["offers"])
    for company, row in healthy.items():
        assert broken[company]["composite_score"] == row["composite_score"], company
        assert broken[company]["rank"] == row["rank"], company


@pytest.mark.parametrize("bad", [{"economic": -1}, {"workload": "abc"}])
def test_invalid_weight_is_rejected(client, bad):
    """权重校验不能被绕过（否则排序会读到非法输入）。"""
    h = _auth_header(client)
    r = client.put("/api/offer/weights", json={"weights": bad}, headers=h)
    assert r.status_code >= 400


# --------------------------------------------------------------------------
# 附注：``app/api/offer.py`` 的连接泄漏**已修复**。
#
#   它曾经是全项目唯一不用 ``Depends(get_db)`` 的路由 —— 自带 ``_db()``，
#   直接 ``return SessionLocal()`` 且从不 close，每个请求漏一个池化连接
#   （默认池 size 5 + overflow 10），请求量一上来就 QueuePool 超时。
#   本文件当初为了不撞上这个坑，把请求数压得很小。
#
#   现在全部端点都走项目标准的 ``Depends(get_db)``（yield + finally close），
#   所以这里的用例已经恢复完整请求体量，并在 ``tests/test_offer.py`` 里新增
#   ``test_offer_routes_release_db_sessions`` 专门守连接生命周期。
# --------------------------------------------------------------------------
