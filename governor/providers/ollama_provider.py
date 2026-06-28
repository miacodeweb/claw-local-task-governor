"""Ollama provider — wraps the existing ollama_client module."""

from __future__ import annotations

import time
from typing import Any

from governor.ollama_client import (
    OllamaClient,
    OllamaConfig,
    OllamaError,
    load_ollama_config,
)
from governor.providers.base import ModelProvider, ProviderHealth, ProviderResponse


class OllamaModelProvider(ModelProvider):
    """Ollama provider backed by governor.ollama_client."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self._config = config or load_ollama_config()
        self._client = OllamaClient(self._config)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def config(self) -> OllamaConfig:
        return self._config

    def list_models(self) -> list[str]:
        try:
            return self._client.list_models()
        except OllamaError:
            return []

    def chat(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResponse:
        started = time.perf_counter()
        client = self._client
        if model != self._config.model:
            from governor.ollama_client import OllamaConfig as OC
            overridden = OC(
                base_url=self._config.base_url,
                model=model,
                temperature=self._config.temperature,
                timeout_seconds=self._config.timeout_seconds,
                max_chars_per_file=self._config.max_chars_per_file,
            )
            client = OllamaClient(overridden)
        try:
            text = client.chat(messages)
            elapsed = (time.perf_counter() - started) * 1000
            return ProviderResponse(
                text=text,
                model=model,
                provider="ollama",
                response_ms=elapsed,
                output_chars=len(text),
            )
        except OllamaError as e:
            raise _to_provider_error(e)

    def healthcheck(self) -> ProviderHealth:
        try:
            self._client.check_ollama_available()
            return ProviderHealth(available=True, provider="ollama")
        except OllamaError as e:
            return ProviderHealth(available=False, provider="ollama", error=str(e))

    def analyze_text(
        self,
        model: str,
        prompt: str,
        text: str,
        max_chars: int | None = None,
        temperature: float = 0.1,
    ) -> ProviderResponse:
        started = time.perf_counter()
        try:
            result = self._client.analyze_text_with_model(prompt, text, max_chars=max_chars)
            elapsed = (time.perf_counter() - started) * 1000
            return ProviderResponse(
                text=result,
                model=model,
                provider="ollama",
                response_ms=elapsed,
                output_chars=len(result),
                input_chars=len(text[:max_chars]) if max_chars else len(text),
            )
        except OllamaError as e:
            raise _to_provider_error(e)


class ProviderError(RuntimeError):
    """Raised when a provider operation fails."""


def _to_provider_error(error: OllamaError) -> ProviderError:
    return ProviderError(str(error))
