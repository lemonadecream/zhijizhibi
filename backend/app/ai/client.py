"""OpenAI-compatible Chat Completions HTTP client.

Talks to any endpoint that implements the OpenAI Chat Completions API
(``/v1/chat/completions``). Model name and base URL come from configuration, so
switching providers is purely an environment change -- no business code touches
a vendor SDK.
"""
from __future__ import annotations

import json

import httpx

from app.logging_config import logger


class ProviderError(Exception):
    """Transport / upstream error from the LLM provider (retryable by the gateway)."""

    def __init__(self, message: str, *, transient: bool = True):
        super().__init__(message)
        self.transient = transient


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    def chat_completion(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        json_mode: bool = True,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = self._http.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            logger.warning("AI request timed out: %s", exc)
            raise ProviderError(f"request timeout after {self.timeout}s", transient=True) from exc
        except httpx.HTTPError as exc:
            logger.warning("AI request failed: %s", exc)
            raise ProviderError(str(exc), transient=True) from exc

        if resp.status_code >= 500 or resp.status_code == 429:
            raise ProviderError(
                f"upstream status {resp.status_code}", transient=True
            )
        if resp.status_code >= 400:
            # auth / quota / bad request -- surface clearly, not retried as transient.
            raise ProviderError(
                f"upstream status {resp.status_code}: {resp.text[:200]}",
                transient=False,
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"unexpected upstream response: {exc}", transient=False) from exc

    def chat_completion_stream(self, messages: list[dict], *, temperature: float = 0.2, max_tokens: int = 2000):
        """Yield raw text deltas from an OpenAI-compatible streaming completion.

        Used by the interview SSE endpoint so the user sees the AI "typing"
        instead of waiting for the full JSON envelope.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            with self._http.stream("POST", url, headers=headers, json=body, timeout=self.timeout) as resp:
                if resp.status_code >= 400:
                    detail = resp.read().decode("utf-8", "replace")[:200]
                    transient = resp.status_code >= 500 or resp.status_code == 429
                    raise ProviderError(f"upstream status {resp.status_code}: {detail}", transient=transient)
                for line in resp.iter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {}).get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
        except httpx.TimeoutException as exc:
            raise ProviderError(f"stream timeout after {self.timeout}s", transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"stream failed: {exc}", transient=True) from exc
