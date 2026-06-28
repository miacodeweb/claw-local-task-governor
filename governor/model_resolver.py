"""Centralized model resolution for LocalScope — zero external dependencies.

Priority:
1. --model explicit override (manual)
2. --use-benchmark-recommendations (delegates to model_recommendations at runtime)
3. config.yaml
4. default (hardcoded fallback)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResolvedModel:
    model: str
    source: str
    confidence: str = "none"
    benchmark_source: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "source": self.source,
            "confidence": self.confidence,
            "benchmark_source": self.benchmark_source,
            "warnings": self.warnings,
        }


def resolve_model(
    *,
    model_override: str | None = None,
    use_benchmark_recommendations: bool = False,
    config_model: str | None = None,
    recommendation: object | None = None,
) -> ResolvedModel:
    """Resolve which model to use.

    When use_benchmark_recommendations is True and recommendation is provided,
    the recommended model from benchmark/model_profiles data is used.
    recommendation should be a ModelRecommendation or dict with .model, .source, .confidence, .warnings.
    """
    if model_override is not None and model_override.strip():
        return ResolvedModel(
            model=model_override.strip(),
            source="manual",
            confidence="high",
        )

    if use_benchmark_recommendations and recommendation is not None:
        rec = recommendation
        model = getattr(rec, "model", "") or ""
        source = getattr(rec, "source", "benchmark") or "benchmark"
        confidence = getattr(rec, "confidence", "low") or "low"
        warnings = list(getattr(rec, "warnings", []) or [])
        return ResolvedModel(
            model=model,
            source="benchmark",
            confidence=confidence,
            benchmark_source=source,
            warnings=warnings,
        )

    if config_model:
        return ResolvedModel(
            model=config_model,
            source="config",
            confidence="none",
        )

    return ResolvedModel(
        model="qwen2.5-coder:7b",
        source="default",
        confidence="none",
    )
