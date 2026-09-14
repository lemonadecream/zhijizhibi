"""AI Gateway unit tests: schema validation, retry, fallback, invalid output.

These construct the gateway with custom providers so no network / API key is
required. They verify the single most important safety property of the gateway:
the business layer never receives a malformed or empty AI result -- either the
schema-valid output comes back, or a deterministic fallback is returned.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.ai.client import OpenAICompatibleClient, ProviderError
from app.ai.gateway import AIResult, AIGateway, F1ResumeParseTask, F2ProfileTask
from app.ai.provider import BaseProvider, MockProvider


# ----------------------------- sample payloads -----------------------------
def valid_f1() -> dict:
    return {
        "education": [{"school": "A大学", "major": "计算机", "degree": "本科",
                        "start": "2020", "end": "2024"}],
        "internships": [{"company": "B公司", "role": "后端", "start": "2023",
                          "end": "2023", "duty": "接口开发"}],
        "projects": [{"name": "P项目", "role": "负责人", "desc": "交易系统"}],
        "skills": [{"name": "Python", "level": 3}],
        "interests": ["后端开发"],
        "signals": [{"type": "preference", "text": "想做技术", "evidence": "简历"}],
    }


def valid_f2() -> dict:
    return {
        "ability_tags": [{"tag": "编程", "level": 3, "confidence": 0.8, "evidence": "实习"}],
        "interest_tags": [{"tag": "后端", "evidence": "简历"}],
        "strengths": [{"item": "有实习经验", "evidence": "B公司"}],
        "risks": [{"item": "缺大项目", "evidence": "小项目", "strategy": "参与开源"}],
        "preference_infer": {"field": "技术"},
    }


def _gateway(provider: BaseProvider) -> AIGateway:
    g = AIGateway(provider)
    for task in g.tasks.values():
        task.retry.backoff = 0.0  # keep tests fast
    return g


# ----------------------------- providers -----------------------------
class FlakyProvider(BaseProvider):
    """Raises transient errors ``fail_times`` then returns ``payload``."""

    def __init__(self, payload: dict, fail_times: int = 1):
        self.payload = payload
        self.fail_times = fail_times
        self.calls = 0

    def chat_json(self, *, system_prompt, user_prompt, output_schema, temperature=0.2, max_tokens=2000):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError("transient upstream hiccup", transient=True)
        return self.payload


class AlwaysFailProvider(BaseProvider):
    def chat_json(self, *, system_prompt, user_prompt, output_schema, temperature=0.2, max_tokens=2000):
        raise ProviderError("permanent outage", transient=True)


class InvalidOutputProvider(BaseProvider):
    """Returns structurally invalid JSON (fails Pydantic validation)."""

    def chat_json(self, *, system_prompt, user_prompt, output_schema, temperature=0.2, max_tokens=2000):
        props = output_schema.get("properties", {})
        if "education" in props:
            return {"education": "not-a-list"}  # F1: wrong type -> ValidationError
        if "ability_tags" in props:
            return {"risks": [{"item": "x", "evidence": "y"}]}  # F2: missing strategy
        return {}


# ----------------------------- tests -----------------------------
def test_f1_schema_validation_ok():
    g = _gateway(MockProvider())
    res = g.run("f1_resume_parse", {"raw_text": "张三 清华 计算机"})
    assert isinstance(res, AIResult)
    assert res.status == "ok"
    assert "education" in res.data
    assert res.data["education"]


def test_f2_schema_validation_ok():
    g = _gateway(MockProvider())
    res = g.run("f2_profile", {"experiences": [{"type": "education", "title": "清华", "detail": ""}]})
    assert res.status == "ok"
    assert "ability_tags" in res.data


def test_retry_then_success():
    prov = FlakyProvider(valid_f1(), fail_times=2)
    g = _gateway(prov)
    res = g.run("f1_resume_parse", {"raw_text": "x"})
    assert res.status == "ok"
    # max_retries=2 -> 3 total attempts; 2 failed + 1 success.
    assert prov.calls == 3


def test_fallback_on_persistent_failure():
    g = _gateway(AlwaysFailProvider())
    res = g.run("f1_resume_parse", {"raw_text": "x"})
    assert res.status == "fallback"
    assert res.fallback_available is True
    assert res.error is not None


def test_invalid_output_triggers_fallback():
    g = _gateway(InvalidOutputProvider())
    res = g.run("f2_profile", {"experiences": []})
    assert res.status == "fallback"
    # F2 fallback returns an empty-but-valid profile.
    assert res.data["ability_tags"] == []


def test_gateway_rejects_unknown_task():
    from app.errors.exceptions import AIGatewayError

    g = _gateway(MockProvider())
    try:
        g.run("does_not_exist", {})
        assert False, "expected AIGatewayError"
    except AIGatewayError:
        pass


def test_client_timeout_is_transient():
    """A real httpx timeout is surfaced as a transient ProviderError."""
    slow = _SlowServer()
    slow.start()

    try:
        client = OpenAICompatibleClient(
            base_url=f"http://127.0.0.1:{slow.port}",
            api_key="x",
            model="m",
            timeout=0.3,
        )
        t0 = time.time()
        try:
            client.chat_completion([{"role": "user", "content": "hi"}])
            assert False, "expected timeout"
        except ProviderError as exc:
            assert exc.transient is True
        # The call should have aborted near the 0.3s timeout, not waited 2s.
        assert time.time() - t0 < 1.5
    finally:
        slow.stop()


class _SlowServer:
    """Minimal OpenAI-style server that replies after a long delay."""

    def __init__(self):
        self._httpd = None
        self.port = 0

    def _handler(self):
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(2)
                body = json.dumps({
                    "choices": [{"message": {"content": "{}"}}]
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        return H

    def start(self):
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
