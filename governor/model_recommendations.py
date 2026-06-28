"""Model recommendations derived from LocalScope benchmark results and model profiles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory
from governor.model_benchmark import DEFAULT_BENCHMARK_OUTPUT_DIR as BENCH_OUTPUT_DIR
from governor.model_profiles import (
    DEFAULT_PROMPT_VERSION,
    DEFAULT_RECOMMENDED_MAX_CHARS,
    ModelProfileStats,
    ModelProfileStore,
)
from governor.ollama_client import OllamaConfig, load_ollama_config


CONFIDENCE_LEVELS = {"none", "low", "medium", "high"}

CONFIDENCE_NONE_MAX_RUNS = 0
CONFIDENCE_LOW_MAX_RUNS = 4
CONFIDENCE_MEDIUM_MAX_RUNS = 14
CONFIDENCE_HIGH_MIN_RUNS = 15

CONFIDENCE_HIGH_JSON_VALID_MIN = 0.85
CONFIDENCE_HIGH_MODEL_FAIL_MAX = 0.10
CONFIDENCE_LOW_JSON_VALID_MIN = 0.50
DEMO_MODEL_NAMES = {"demo-model", "test-model", "mock-model"}


@dataclass(frozen=True)
class ModelRecommendation:
    model: str
    prompt_version: str
    max_chars: int
    source: str
    confidence: str
    best_json_model: str | None
    fastest_model: str | None
    most_stable_model: str | None
    last_benchmark: str | None
    warnings: list[str]
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_version": self.prompt_version,
            "max_chars": self.max_chars,
            "source": self.source,
            "confidence": self.confidence,
            "best_json_model": self.best_json_model,
            "fastest_model": self.fastest_model,
            "most_stable_model": self.most_stable_model,
            "last_benchmark": self.last_benchmark,
            "warnings": self.warnings,
            "suggestion": self.suggestion,
        }


def get_model_recommendations(
    *,
    task_type: str | None = None,
    profile: str = "general",
    latest_benchmark: bool = False,
    memory: SQLiteMemory | None = None,
    benchmark_dir: Path | str = BENCH_OUTPUT_DIR,
    include_demo_models: bool = False,
) -> ModelRecommendation:
    task_memory = memory or SQLiteMemory(DEFAULT_MEMORY_PATH)
    profile_store = task_memory.model_profile_store()
    config = load_ollama_config()
    warnings: list[str] = []

    benchmark_data = None
    benchmark_path = None
    if latest_benchmark:
        benchmark_path = _find_latest_benchmark(benchmark_dir)
        if benchmark_path is not None:
            benchmark_data = _load_benchmark_json(benchmark_path)
        else:
            warnings.append("no benchmark reports found")

    all_profiles = profile_store.list_profiles()
    filtered = _filter_profiles(
        all_profiles,
        task_type=task_type,
        profile=profile,
        include_demo_models=include_demo_models,
        warnings=warnings,
    )

    if filtered:
        best = _select_best_profile(filtered)
        confidence, conf_warnings = _compute_confidence(best, profile_name=profile)
        warnings.extend(conf_warnings)
        suggestion = _build_suggestion(confidence, profile, task_type)
        recommendation = ModelRecommendation(
            model=best.model,
            prompt_version=best.prompt_version,
            max_chars=best.recommended_max_chars,
            source="model_profiles",
            confidence=confidence,
            best_json_model=_best_json_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
            fastest_model=_fastest_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
            most_stable_model=_most_stable_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
            last_benchmark=str(benchmark_path) if benchmark_path else None,
            warnings=warnings,
            suggestion=suggestion,
        )
    elif benchmark_data is not None:
        bench_model = _best_benchmark_model(
            benchmark_data,
            include_demo_models=include_demo_models,
            warnings=warnings,
        )
        if bench_model:
            bench_models = benchmark_data.get("models", [])
            bench_stats = next((m for m in bench_models if m.get("model") == bench_model), None)
            recommendation = ModelRecommendation(
                model=bench_model,
                prompt_version=bench_stats.get("recommended_prompt_version", DEFAULT_PROMPT_VERSION) if bench_stats else DEFAULT_PROMPT_VERSION,
                max_chars=bench_stats.get("recommended_max_chars", DEFAULT_RECOMMENDED_MAX_CHARS) if bench_stats else DEFAULT_RECOMMENDED_MAX_CHARS,
                source="benchmark",
                confidence="low" if bench_stats is None else "medium",
                best_json_model=_best_json_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
                fastest_model=_fastest_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
                most_stable_model=_most_stable_from_benchmark(benchmark_data, include_demo_models=include_demo_models),
                last_benchmark=str(benchmark_path),
                warnings=warnings,
                suggestion="run benchmark-profile to collect more data per profile",
            )
        else:
            recommendation = _fallback_recommendation(
                config,
                warnings,
                benchmark_path,
                include_demo_models=include_demo_models,
            )
    else:
        recommendation = _fallback_recommendation(
            config,
            warnings,
            benchmark_path,
            include_demo_models=include_demo_models,
        )

    return recommendation


def resolve_benchmark_model(
    *,
    model_override: str | None,
    use_benchmark_recommendations: bool,
    config_model: str,
    task_type: str | None = None,
    profile: str = "general",
    benchmark_dir: Path | str = BENCH_OUTPUT_DIR,
    memory: SQLiteMemory | None = None,
) -> tuple[str, str]:
    if model_override is not None:
        return model_override, "explicit_manual_override"
    if use_benchmark_recommendations:
        rec = get_model_recommendations(
            task_type=task_type,
            profile=profile,
            latest_benchmark=True,
            benchmark_dir=benchmark_dir,
            memory=memory,
        )
        return rec.model, f"benchmark:{rec.source}:confidence={rec.confidence}"
    return config_model, "config_file"


def _filter_profiles(
    profiles: list[ModelProfileStats],
    task_type: str | None,
    profile: str,
    *,
    include_demo_models: bool = False,
    warnings: list[str] | None = None,
) -> list[ModelProfileStats]:
    filtered = [p for p in profiles if p.runs_count > 0]
    if not include_demo_models:
        before = len(filtered)
        filtered = [p for p in filtered if not is_demo_model_name(p.model)]
        excluded = before - len(filtered)
        if excluded and warnings is not None:
            warnings.append(f"ignored {excluded} demo/test model profile record(s)")
    if task_type:
        filtered = [p for p in filtered if p.task_type == task_type]
    if profile and profile != "auto":
        filtered = [p for p in filtered if p.profile == profile]
    return filtered


def _select_best_profile(profiles: list[ModelProfileStats]) -> ModelProfileStats:
    return max(
        profiles,
        key=lambda p: (
            p.json_valid_rate,
            p.success_rate,
            -p.json_fail_rate,
            -p.model_fail_rate,
            p.runs_count,
        ),
    )


def _compute_confidence(stats: ModelProfileStats, *, profile_name: str = "general") -> tuple[str, list[str]]:
    """Return (confidence_level, list_of_warnings)."""
    warnings: list[str] = []
    runs = stats.runs_count

    if runs <= CONFIDENCE_NONE_MAX_RUNS:
        return "none", [f"no usable samples for profile {profile_name}"]

    if runs <= CONFIDENCE_LOW_MAX_RUNS:
        warnings.append(
            f"only {runs} sample(s) for profile {profile_name}"
        )
        return "low", warnings

    if runs <= CONFIDENCE_MEDIUM_MAX_RUNS:
        if stats.json_valid_rate < CONFIDENCE_LOW_JSON_VALID_MIN:
            warnings.append(
                f"json_valid_rate={stats.json_valid_rate:.2f} is below {CONFIDENCE_LOW_JSON_VALID_MIN:.2f} "
                f"with {runs} samples"
            )
        return "medium", warnings

    if stats.json_valid_rate < CONFIDENCE_HIGH_JSON_VALID_MIN:
        warnings.append(
            f"json_valid_rate={stats.json_valid_rate:.2f} is below {CONFIDENCE_HIGH_JSON_VALID_MIN:.2f} "
            f"for high confidence"
        )
        return "medium", warnings

    if stats.model_fail_rate > CONFIDENCE_HIGH_MODEL_FAIL_MAX:
        warnings.append(
            f"model_fail_rate={stats.model_fail_rate:.2f} exceeds {CONFIDENCE_HIGH_MODEL_FAIL_MAX:.2f}"
        )
        return "medium", warnings

    return "high", warnings


def _build_suggestion(confidence: str, profile: str, task_type: str | None) -> str:
    if confidence in ("none", "low"):
        parts = [f"run benchmark-profile {profile}"]
        if task_type:
            parts.append(f"--prompt-versions v1")
        parts.append("--models <your-models>")
        return " ".join(parts)
    if confidence == "medium":
        return f"consider running more tasks for profile {profile} to reach high confidence"
    return ""


def _find_latest_benchmark(benchmark_dir: Path | str) -> Path | None:
    dir_path = Path(benchmark_dir)
    if not dir_path.is_dir():
        return None
    candidates = list(dir_path.glob("benchmark-*.json")) + list(dir_path.glob("profile-benchmark-*.json"))
    candidates.sort(reverse=True)
    return candidates[0] if candidates else None


def _load_benchmark_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _best_json_from_benchmark(data: dict[str, Any] | None, *, include_demo_models: bool = False) -> str | None:
    return _summary_model_from_benchmark(data, "best_json_model", include_demo_models=include_demo_models)


def _fastest_from_benchmark(data: dict[str, Any] | None, *, include_demo_models: bool = False) -> str | None:
    return _summary_model_from_benchmark(data, "fastest_model", include_demo_models=include_demo_models)


def _most_stable_from_benchmark(data: dict[str, Any] | None, *, include_demo_models: bool = False) -> str | None:
    return _summary_model_from_benchmark(data, "most_stable_model", include_demo_models=include_demo_models)


def _summary_model_from_benchmark(
    data: dict[str, Any] | None,
    key: str,
    *,
    include_demo_models: bool = False,
) -> str | None:
    if data is None:
        return None
    model = data.get("summary", {}).get(key)
    if not include_demo_models and is_demo_model_name(model):
        return None
    return model


def is_demo_model_name(model_name: str | None) -> bool:
    normalized = str(model_name or "").strip().lower()
    if normalized in DEMO_MODEL_NAMES:
        return True
    return normalized.startswith(("demo-", "test-", "mock-"))


def _best_benchmark_model(
    data: dict[str, Any] | None,
    *,
    include_demo_models: bool,
    warnings: list[str],
) -> str | None:
    if data is None:
        return None

    summary_model = data.get("summary", {}).get("best_overall_model")
    if include_demo_models or not is_demo_model_name(summary_model):
        return summary_model

    if summary_model:
        warnings.append("ignored demo/test benchmark model")

    candidates = [
        item for item in data.get("models", [])
        if not is_demo_model_name(item.get("model"))
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda item: item.get("overall_score", 0))
    return best.get("model")


def _fallback_recommendation(
    config: OllamaConfig,
    warnings: list[str],
    benchmark_path: Path | None,
    *,
    include_demo_models: bool = False,
) -> ModelRecommendation:
    model = config.model
    if not include_demo_models and is_demo_model_name(model):
        warnings.append("ignored demo/test config model")
        model = OllamaConfig.model
    warnings.append("no model profile data or benchmark results available; using config.yaml default")
    return ModelRecommendation(
        model=model,
        prompt_version=DEFAULT_PROMPT_VERSION,
        max_chars=config.max_chars_per_file,
        source="config.yaml",
        confidence="none",
        best_json_model=None,
        fastest_model=None,
        most_stable_model=None,
        last_benchmark=str(benchmark_path) if benchmark_path else None,
        warnings=warnings,
        suggestion="run benchmark-profile and calibrate-models to collect data",
    )
