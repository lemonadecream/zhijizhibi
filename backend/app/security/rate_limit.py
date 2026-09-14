"""In-process sliding-window rate limiter (login / register brute-force guard).

MVP trade-off, consistent with the in-process BackgroundTasks choice in
``app/services/jobs.py``: single-host deployment keeps state in the process.
Limitations (documented, accepted):
  * per-process — a multi-worker/multi-node deployment needs a shared store (Redis);
  * reset on restart — acceptable: an attacker loses at most one window.

Keys are composed by the caller (e.g. ip + identifier). Only *failed* attempts
are recorded via :meth:`hit`; successful auth calls :meth:`reset`.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """True if ``key`` is still under the limit (without recording an event)."""
        with self._lock:
            self._prune(key)
            return len(self._events[key]) < self.max_events

    def hit(self, key: str) -> bool:
        """Record one event. Returns False when the key is now over the limit."""
        with self._lock:
            self._prune(key)
            q = self._events[key]
            q.append(time.monotonic())
            return len(q) <= self.max_events

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset_all(self) -> None:
        """Clear all counters (test isolation / ops manually unblocking)."""
        with self._lock:
            self._events.clear()

    def _prune(self, key: str) -> None:
        q = self._events.get(key)
        if not q:
            return
        cutoff = time.monotonic() - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            self._events.pop(key, None)
