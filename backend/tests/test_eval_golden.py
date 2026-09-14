"""Golden-set structural checks in CI (mock provider, no network / no cost).

Real-model quality evaluation runs offline via `python -m evals.run_evals`
(needs a real AI_API_KEY). Here we run the SAME golden cases through the
gateway with the mock provider: the rubric's contract-level rules
(enum / coverage / discipline / faithfulness-by-substring) verify that
gateway → schema validation → business rules stay intact as code evolves.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai.gateway import get_gateway
from evals.run_evals import check_case

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "evals" / "golden_cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_case_contract(case):
    """每个黄金用例在 mock provider 下必须跑通且通过契约级 rubric。

    mock 返回固定内容，与"内容质量"相关的检查（coverage / evidence /
    invention / discipline 数字纪律）只有真实模型才有意义，留离线评测
    （evals.run_evals + 真实 key）覆盖。CI 锁的是任务管道契约：
    路由 → schema 校验 → 业务规则 → 枚举完整 → 不回显输入。
    """
    skip_prefixes = ("coverage", "evidence", "invention", "discipline")
    result = get_gateway().run(case["task"], case["input"])
    assert result.status == "ok", f"mock provider 不应降级：{result.error}"

    ok, failures = check_case(case, result.data)
    hard = [f for f in failures if not f.startswith(skip_prefixes)]
    assert not hard, f"契约检查未通过：{hard}"


def test_gateway_metrics_recorded(client):
    """网关每次调用都应产生指标：ok/降级计数 + 延迟（P0-AI 可观测性）。"""
    from app.ai.metrics import metrics

    metrics.reset()
    h = client.post(
        "/api/auth/register",
        json={"email": "metrics-probe@test.com", "password": "secret123", "name": "标"},
    )
    token = h.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/experience",
        json={
            "education": [{"school": "浙大", "major": "计算机", "degree": "本科", "start": "2019", "end": "2023"}],
            "internships": [{"company": "阿里", "role": "产品实习生", "start": "2022", "end": "2022", "detail": "需求分析"}],
            "projects": [],
            "skills": [{"name": "SQL", "level": 4}],
            "interests": ["数据分析"],
        },
        headers=headers,
    )
    client.post("/api/profile/generate", json={}, headers=headers)

    snap = metrics.snapshot()
    assert any("f1" in t or "f2" in t for t in snap), f"应有 AI 调用指标：{snap.keys()}"
    for task, s in snap.items():
        assert s["total"] == s["ok"] + s["fallback"] + s["error"], f"{task} 计数不一致"
        assert s["avg_ms"] >= 0

    # 指标端点（登录可读，聚合数据）：结构与计数一致性
    r = client.get("/api/config/ai-stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    for task, s in body["tasks"].items():
        assert {"total", "ok", "fallback", "error", "avg_ms", "max_ms"} <= set(s)

    # 未登录不可读
    assert client.get("/api/config/ai-stats").status_code == 401
