"""AI call metrics (in-process; MVP single-host deployment).

Records one stat per gateway task: total / ok / fallback / error counts plus
latency. Purpose:
  * cost & reliability visibility per AI task (PM-facing: 每个功能花多少钱、
    降级率多高，一问就有数)；
  * the eval runner and future admin endpoint read from the same source.

In-process like the rate limiter: per-process numbers, reset on restart.
A multi-worker deployment swaps this for a shared store behind the same API.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class TaskStats:
    total: int = 0
    ok: int = 0
    fallback: int = 0
    error: int = 0
    total_latency_ms: int = 0
    max_latency_ms: int = 0
    last_error: str = ""


class AIMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._stats: dict[str, TaskStats] = defaultdict(TaskStats)

    def record(self, task: str, status: str, latency_ms: int, error: str = "") -> None:
        with self._lock:
            s = self._stats[task]
            s.total += 1
            if status == "ok":
                s.ok += 1
            elif status == "fallback":
                s.fallback += 1
            else:
                s.error += 1
            s.total_latency_ms += latency_ms
            s.max_latency_ms = max(s.max_latency_ms, latency_ms)
            if error:
                s.last_error = error[:200]

    def snapshot(self) -> dict:
        """Return {task: {total, ok, fallback, error, avg_ms, max_ms, last_error}}."""
        with self._lock:
            out: dict = {}
            for task, s in self._stats.items():
                out[task] = {
                    "total": s.total,
                    "ok": s.ok,
                    "fallback": s.fallback,
                    "error": s.error,
                    "avg_ms": round(s.total_latency_ms / s.total) if s.total else 0,
                    "max_ms": s.max_latency_ms,
                    "last_error": s.last_error,
                }
            return out

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()


metrics = AIMetrics()
