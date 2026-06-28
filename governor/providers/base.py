"""Base classes for LocalScope model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    provider: str
    response_ms: float = 0.0
    input_chars: int = 0
    output_chars: int = 0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "response_ms": self.response_ms,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
        }


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    provider: str
    error: str = ""


class ModelProvider(ABC):
    """Abstract base for local model providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    def chat(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResponse: ...

    @abstractmethod
    def healthcheck(self) -> ProviderHealth: ...

    def analyze_text(
        self,
        model: str,
        prompt: str,
        text: str,
        max_chars: int | None = None,
        temperature: float = 0.1,
    ) -> ProviderResponse:
        bounded = text[:max_chars] if max_chars else text
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": bounded},
        ]
        return self.chat(model, messages)
