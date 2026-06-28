"""Provider registry for LocalScope."""

from __future__ import annotations

from typing import Any

from governor.providers.base import ModelProvider, ProviderHealth
from governor.providers.ollama_provider import OllamaModelProvider
from governor.ollama_client import OllamaConfig, load_ollama_config


_registry: dict[str, ModelProvider] = {}


def _init_registry() -> None:
    if _registry:
        return
    _registry["ollama"] = OllamaModelProvider()
    try:
        from governor.providers.openai_compatible_provider import OpenAiCompatProvider
        oai = OpenAiCompatProvider()
        _registry["openai_compatible"] = oai
    except ImportError:
        pass


def list_providers() -> list[str]:
    _init_registry()
    return sorted(_registry.keys())


def get_provider(name: str) -> ModelProvider | None:
    _init_registry()
    return _registry.get(name)


def all_providers_health() -> dict[str, dict[str, Any]]:
    _init_registry()
    result: dict[str, dict[str, Any]] = {}
    for name, provider in _registry.items():
        health = provider.healthcheck()
        result[name] = {
            "available": health.available,
            "provider": health.provider,
            "error": health.error,
        }
    return result


def list_models_for_provider(name: str) -> list[str]:
    provider = get_provider(name)
    if provider is None:
        return []
    try:
        return provider.list_models()
    except Exception:
        return []
