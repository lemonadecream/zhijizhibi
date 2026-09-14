"""SlidingWindowLimiter unit tests (login/register rate limiting).

Uses a controllable fake clock instead of real sleeps so the window-expiry
behavior is deterministic in CI.
"""
from __future__ import annotations

import pytest

from app.security.rate_limit import SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    fc = FakeClock()
    monkeypatch.setattr("app.security.rate_limit.time", fc)
    return fc


def test_allows_under_limit_and_blocks_over(clock):
    limiter = SlidingWindowLimiter(max_events=3, window_seconds=60)
    key = "login:ip:-user"

    assert limiter.allow(key)
    for _ in range(3):
        assert limiter.hit(key)
    assert not limiter.allow(key)
    assert not limiter.hit(key)  # 第 4 次失败也被拒绝计数


def test_window_expiry_restores_access(clock):
    limiter = SlidingWindowLimiter(max_events=2, window_seconds=30)
    key = "login:ip:user"

    limiter.hit(key)
    limiter.hit(key)
    assert not limiter.allow(key)

    clock.now += 31  # 窗口滑过，旧事件过期
    assert limiter.allow(key)
    assert limiter.hit(key)


def test_keys_are_independent(clock):
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
    limiter.hit("login:ip:a")
    assert not limiter.allow("login:ip:a")
    assert limiter.allow("login:ip:b")


def test_reset_clears_single_key(clock):
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
    limiter.hit("login:ip:a")
    limiter.reset("login:ip:a")
    assert limiter.allow("login:ip:a")


def test_reset_all_clears_everything(clock):
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
    limiter.hit("k1")
    limiter.hit("k2")
    limiter.reset_all()
    assert limiter.allow("k1") and limiter.allow("k2")
