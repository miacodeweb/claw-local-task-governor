"""Adaptive content limits based on operational model profile metrics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governor.model_profiles import DEFAULT_PROMPT_VERSION, ModelProfileStats, ModelProfileStore
from governor.ollama_client import EXAMPLE_CONFIG_PATH, DEFAULT_CONFIG_PATH, _parse_simple_yaml


@dataclass(frozen=True)
class AdaptiveLimitsConfig:
    enabled: bool = True
    default_max_chars: int = 12000
    min_max_chars: int = 4000
    hard_max_chars: int = 20000
    reduce_on_json_fail_rate: float = 0.30
    reduce_on_model_fail_rate: float = 0.20
    increase_on_success_rate: float = 0.90
    increase_on_json_valid_rate: float = 0.85
    truncation_rate_for_growth: float = 0.50
    adjustment_step_percent: int = 20
    min_runs_for_history: int = 3


@dataclass(frozen=True)
class AdaptiveLimitDecision:
    effective_max_chars: int
    enabled: bool
    reason: str
    source: str
    profile_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_max_chars": self.effective_max_chars,
            "enabled": self.enabled,
            "reason": self.reason,
            "source": self.source,
            "profile_runs": self.profile_runs,
        }


def load_adaptive_limits_config(
    config_path: Path | str | None = None,
    *,
    fallback_default_max_chars: int = 12000,
) -> AdaptiveLimitsConfig:
    path = _select_config_path(config_path)
    if path is None:
        return AdaptiveLimitsConfig(default_max_chars=fallback_default_max_chars)

    parsed = _parse_simple_yaml(path)
    section = parsed.get("adaptive_limits", {})
    return AdaptiveLimitsConfig(
        enabled=bool(section.get("enabled", AdaptiveLimitsConfig.enabled)),
        default_max_chars=int(section.get("default_max_chars", fallback_default_max_chars)),
        min_max_chars=int(section.get("min_max_chars", AdaptiveLimitsConfig.min_max_chars)),
        hard_max_chars=int(section.get("hard_max_chars", AdaptiveLimitsConfig.hard_max_chars)),
        reduce_on_json_fail_rate=float(
            section.get("reduce_on_json_fail_rate", AdaptiveLimitsConfig.reduce_on_json_fail_rate)
        ),
        reduce_on_model_fail_rate=float(
            section.get("reduce_on_model_fail_rate", AdaptiveLimitsConfig.reduce_on_model_fail_rate)
        ),
        increase_on_success_rate=float(
            section.get("increase_on_success_rate", AdaptiveLimitsConfig.increase_on_success_rate)
        ),
        increase_on_json_valid_rate=float(
            section.get("increase_on_json_valid_rate", AdaptiveLimitsConfig.increase_on_json_valid_rate)
        ),
        adjustment_step_percent=int(
            section.get("adjustment_step_percent", AdaptiveLimitsConfig.adjustment_step_percent)
        ),
    )


def resolve_effective_max_chars(
    *,
    model: str,
    task_type: str,
    profile: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    store: ModelProfileStore | None,
    config: AdaptiveLimitsConfig,
    fixed_max_chars: int,
    enabled: bool = True,
) -> AdaptiveLimitDecision:
    fixed_value = int(fixed_max_chars)
    default_value = _clamp(config.default_max_chars or fixed_max_chars, config.min_max_chars, config.hard_max_chars)
    if not enabled or not config.enabled:
        return AdaptiveLimitDecision(
            effective_max_chars=fixed_value,
            enabled=False,
            reason="adaptive_limits_disabled",
            source="fixed_config",
        )

    stats = None
    if store is not None:
        stats = store.get_profile(
            model=model,
            task_type=task_type,
            profile=profile,
            prompt_version=prompt_version,
        )
    return decision_from_profile(stats, config=config, default_max_chars=default_value)


def decision_from_profile(
    stats: ModelProfileStats | None,
    *,
    config: AdaptiveLimitsConfig,
    default_max_chars: int | None = None,
) -> AdaptiveLimitDecision:
    default_value = _clamp(
        int(default_max_chars or config.default_max_chars),
        config.min_max_chars,
        config.hard_max_chars,
    )
    if stats is None:
        return AdaptiveLimitDecision(
            effective_max_chars=default_value,
            enabled=config.enabled,
            reason="no_model_history",
            source="config_default",
        )

    if stats.runs_count < config.min_runs_for_history:
        return AdaptiveLimitDecision(
            effective_max_chars=default_value,
            enabled=config.enabled,
            reason=f"insufficient_history:runs={stats.runs_count}",
            source="config_default",
            profile_runs=stats.runs_count,
        )

    base = _clamp(stats.recommended_max_chars, config.min_max_chars, config.hard_max_chars)
    reduction_factor = 1 - (config.adjustment_step_percent / 100)
    gentle_growth_factor = 1 + ((config.adjustment_step_percent / 2) / 100)

    if stats.json_fail_rate > config.reduce_on_json_fail_rate:
        return AdaptiveLimitDecision(
            effective_max_chars=_clamp(int(base * reduction_factor), config.min_max_chars, config.hard_max_chars),
            enabled=config.enabled,
            reason=f"reduced:json_fail_rate={stats.json_fail_rate:.2f}",
            source="model_profile",
            profile_runs=stats.runs_count,
        )

    if stats.model_fail_rate > config.reduce_on_model_fail_rate:
        return AdaptiveLimitDecision(
            effective_max_chars=_clamp(int(base * reduction_factor), config.min_max_chars, config.hard_max_chars),
            enabled=config.enabled,
            reason=f"reduced:model_fail_rate={stats.model_fail_rate:.2f}",
            source="model_profile",
            profile_runs=stats.runs_count,
        )

    if (
        stats.success_rate > config.increase_on_success_rate
        and stats.json_valid_rate > config.increase_on_json_valid_rate
    ):
        reason = f"increased:success_rate={stats.success_rate:.2f},json_valid_rate={stats.json_valid_rate:.2f}"
        if stats.truncation_rate > config.truncation_rate_for_growth:
            reason += f",truncation_rate={stats.truncation_rate:.2f}"
        return AdaptiveLimitDecision(
            effective_max_chars=_clamp(int(base * gentle_growth_factor), config.min_max_chars, config.hard_max_chars),
            enabled=config.enabled,
            reason=reason,
            source="model_profile",
            profile_runs=stats.runs_count,
        )

    return AdaptiveLimitDecision(
        effective_max_chars=base,
        enabled=config.enabled,
        reason="kept:profile_within_thresholds",
        source="model_profile",
        profile_runs=stats.runs_count,
    )


def recommendations_for_profiles(
    profiles: list[ModelProfileStats],
    *,
    config: AdaptiveLimitsConfig,
) -> list[dict[str, Any]]:
    recommendations = []
    for stats in profiles:
        decision = decision_from_profile(stats, config=config)
        item = stats.to_dict()
        item.update(
            {
                "effective_max_chars": decision.effective_max_chars,
                "adaptive_limits_enabled": decision.enabled,
                "adaptive_reason": decision.reason,
                "adaptive_source": decision.source,
            }
        )
        recommendations.append(item)
    return recommendations


def _select_config_path(config_path: Path | str | None) -> Path | None:
    if config_path is not None:
        path = Path(config_path)
        return path if path.exists() else None
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if EXAMPLE_CONFIG_PATH.exists():
        return EXAMPLE_CONFIG_PATH
    return None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    low = min(minimum, maximum)
    high = max(minimum, maximum)
    return max(low, min(high, int(value)))
