"""OpenAI-compatible provider for generic endpoints (LM Studio, vLLM, etc.).

Uses environment variables by default:
  LOCAL_SCOPE_OPENAI_COMPAT_BASE_URL
  LOCAL_SCOPE_OPENAI_COMPAT_API_KEY
  LOCAL_SCOPE_OPENAI_COMPAT_MODEL

No real API keys are stored in config files.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from governor.providers.base import ModelProvider, ProviderHealth, ProviderResponse


DEFAULT_TIMEOUT = 120


class OpenAiCompatProvider(ModelProvider):
    """Generic provider for OpenAI-compatible API endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url or os.environ.get("LOCAL_SCOPE_OPENAI_COMPAT_BASE_URL", "")
        self._api_key = api_key or os.environ.get("LOCAL_SCOPE_OPENAI_COMPAT_API_KEY", "")
        self._model = model or os.environ.get("LOCAL_SCOPE_OPENAI_COMPAT_MODEL", "")
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def configured_model(self) -> str:
        return self._model

    def list_models(self) -> list[str]:
        if not self._base_url:
            return []
        try:
            resp = self._request("GET", "/models")
            models = resp.get("data", [])
            return [m.get("id", "") for m in models if isinstance(m, dict) and m.get("id")]
        except Exception:
            return []

    def chat(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResponse:
        if not self._base_url:
            raise ProviderError("openai_compatible base_url is not configured")

        resolved_model = model or self._model
        started = time.perf_counter()
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "stream": False,
        }

        resp = self._request("POST", "/chat/completions", payload)
        choices = resp.get("choices", [])
        if not choices:
            raise ProviderError("no choices in response")

        text = choices[0].get("message", {}).get("content", "")
        elapsed = (time.perf_counter() - started) * 1000

        return ProviderResponse(
            text=text,
            model=resolved_model,
            provider="openai_compatible",
            response_ms=elapsed,
            output_chars=len(text),
            raw_metadata={
                "usage": resp.get("usage", {}),
                "id": resp.get("id", ""),
            },
        )

    def healthcheck(self) -> ProviderHealth:
        if not self._base_url:
            return ProviderHealth(
                available=False,
                provider="openai_compatible",
                error="base_url is not configured; set LOCAL_SCOPE_OPENAI_COMPAT_BASE_URL",
            )
        try:
            self._request("GET", "/models")
            return ProviderHealth(available=True, provider="openai_compatible")
        except Exception as e:
            return ProviderHealth(available=False, provider="openai_compatible", error=str(e))

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        url = f"{self._base_url.rstrip('/')}{path}"
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
        except Exception as e:
            raise ProviderError(str(e))


class ProviderError(RuntimeError):
    """Raised when a provider operation fails."""
