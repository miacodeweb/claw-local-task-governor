"""Profile-based model benchmark: compare models per project type using calibration fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory
from governor.model_benchmark import (
    BenchmarkDryRun,
    BenchmarkReport,
    DEFAULT_BENCHMARK_OUTPUT_DIR,
    DEFAULT_MAX_TASKS,
    ModelBenchmarkStats,
    _aggregate_stats,
    _compute_summary,
    BenchmarkTaskResult,
)
from governor.ollama_client import OllamaClient, load_ollama_config


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "calibration_projects"

PROFILE_FIXTURES: dict[str, str] = {
    "python": "python_project",
    "javascript": "javascript_project",
    "java": "java_project",
    "php": "php_project",
    "wordpress": "wordpress_project",
    "docker": "docker_project",
    "config_files": "config_files_project",
    "windows_folder": "windows_folder",
    "linux_folder": "linux_folder",
    "documentation": "documentation_project",
}

ALLOWED_PROFILES = set(PROFILE_FIXTURES.keys()) | {"all", "general"}


@dataclass(frozen=True)
class ProfileBenchmarkReport:
    metadata: dict[str, Any]
    profiles: dict[str, dict[str, Any]]
    global_summary: dict[str, str | None]
    errors: list[str]


def run_profile_benchmark(
    *,
    profiles: list[str],
    models: list[str],
    max_tasks: int = DEFAULT_MAX_TASKS,
    prompt_versions: list[str] | None = None,
    no_adaptive_limits: bool = False,
    timeout_seconds: int | None = None,
    delay_between_models: int = 0,
    output_dir: Path | str = DEFAULT_BENCHMARK_OUTPUT_DIR,
    dry_run: bool = False,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> ProfileBenchmarkReport | BenchmarkDryRun:
    created_at = _utc_now()
    resolved_profiles = _resolve_profiles(profiles)

    if not resolved_profiles:
        return ProfileBenchmarkReport(
            metadata={"created_at": created_at, "profiles": [], "models": models, "max_tasks": max_tasks},
            profiles={},
            global_summary={"best_general_model": None, "most_consistent_model": None},
            errors=["no valid profiles selected"],
        )

    if dry_run:
        config = client.config if client is not None else load_ollama_config()
        effective_timeout = timeout_seconds or config.timeout_seconds
        estimated_timeout_seconds = len(models) * len(resolved_profiles) * max_tasks * effective_timeout
        return BenchmarkDryRun(
            models=list(models),
            tasks=[{"profile": p, "fixture": _fixture_path(p)} for p in resolved_profiles],
            prompt_versions=list(prompt_versions or ["v1"]),
            project_path="calibration_projects",
            max_tasks=max_tasks,
            output_dir=str(output_dir),
            timeout_seconds=effective_timeout,
            delay_between_models=delay_between_models,
            estimated_timeout_seconds=estimated_timeout_seconds,
        )

    all_errors: list[str] = []
    profile_results: dict[str, dict[str, Any]] = {}
    config = client.config if client is not None else load_ollama_config()
    output_path = Path(output_dir)

    for profile_name in resolved_profiles:
        fixture = _fixture_path(profile_name)
        if fixture is None:
            all_errors.append(f"profile {profile_name}: fixture not found")
            continue

        try:
            from governor.model_benchmark import run_benchmark as single_benchmark
        except ImportError:
            all_errors.append(f"profile {profile_name}: benchmark module unavailable")
            continue

        report = single_benchmark(
            fixture,
            models=models,
            max_tasks=max_tasks,
            profile=profile_name,
            prompt_versions=prompt_versions,
            no_adaptive_limits=no_adaptive_limits,
            timeout_seconds=timeout_seconds,
            delay_between_models=delay_between_models,
            output_dir=output_path,
            dry_run=False,
            client=client,
            memory=memory,
        )

        if isinstance(report, BenchmarkDryRun):
            continue

        summary = report.summary if isinstance(report, BenchmarkReport) else {}
        errors = report.errors if isinstance(report, BenchmarkReport) else []
        all_errors.extend(errors)

        profile_results[profile_name] = {
            "best_overall_model": summary.get("best_overall_model"),
            "best_json_model": summary.get("best_json_model"),
            "fastest_model": summary.get("fastest_model"),
            "most_stable_model": summary.get("most_stable_model"),
            "models": report.models if isinstance(report, BenchmarkReport) else [],
        }

    global_summary = _build_global_summary(profile_results)

    report = ProfileBenchmarkReport(
        metadata={
            "created_at": created_at,
            "profiles": resolved_profiles,
            "models": models,
            "max_tasks": max_tasks,
        },
        profiles=profile_results,
        global_summary=global_summary,
        errors=all_errors,
    )

    _write_profile_benchmark_reports(report, output_path)
    return report


def _resolve_profiles(requested: list[str]) -> list[str]:
    if not requested:
        return []
    if "all" in requested:
        return sorted(p for p in PROFILE_FIXTURES if _fixture_path(p) is not None)
    if "general" in requested:
        result = ["general"]
        result.extend(p for p in requested if p != "general")
        return result
    return [p for p in requested if p in PROFILE_FIXTURES]


def _fixture_path(profile_name: str) -> Path | None:
    dir_name = PROFILE_FIXTURES.get(profile_name)
    if dir_name is None:
        return None
    path = FIXTURE_DIR / dir_name
    return path if path.is_dir() else None


def _build_global_summary(profile_results: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    model_scores: dict[str, float] = {}
    model_counts: dict[str, int] = {}
    for profile_data in profile_results.values():
        for m in profile_data.get("models", []):
            name = m.get("model")
            if name is None:
                continue
            score = m.get("overall_score", 0)
            model_scores[name] = model_scores.get(name, 0.0) + score
            model_counts[name] = model_counts.get(name, 0) + 1

    if not model_scores:
        return {"best_general_model": None, "most_consistent_model": None}

    best_general = max(model_scores, key=model_scores.get)

    per_profile_ranks: dict[str, int] = {}
    for profile_data in profile_results.values():
        models_ranked = sorted(
            profile_data.get("models", []),
            key=lambda m: m.get("overall_score", 0),
            reverse=True,
        )
        for rank, m in enumerate(models_ranked):
            name = m.get("model")
            if name is None:
                continue
            per_profile_ranks[name] = per_profile_ranks.get(name, 0) + rank

    most_consistent = min(per_profile_ranks, key=per_profile_ranks.get) if per_profile_ranks else None

    return {"best_general_model": best_general, "most_consistent_model": most_consistent}


def _write_profile_benchmark_reports(report: ProfileBenchmarkReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"profile-benchmark-{stamp}.json"
    md_path = output_dir / f"profile-benchmark-{stamp}.md"

    data = {
        "metadata": report.metadata,
        "profiles": report.profiles,
        "global_summary": report.global_summary,
        "errors": report.errors,
    }
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(_render_profile_benchmark_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_profile_benchmark_markdown(report: ProfileBenchmarkReport) -> str:
    lines = [
        "# LocalScope Profile Model Benchmark",
        "",
        f"**Generated:** {report.metadata.get('created_at', '')}",
        f"**Profiles:** {', '.join(report.metadata.get('profiles', []))}",
        f"**Models:** {', '.join(report.metadata.get('models', []))}",
        f"**Max tasks:** {report.metadata.get('max_tasks', 0)}",
        "",
        "## Global Summary",
        f"- Best general model: {report.global_summary.get('best_general_model') or 'N/A'}",
        f"- Most consistent model: {report.global_summary.get('most_consistent_model') or 'N/A'}",
        "",
        "## Per-Profile Results",
    ]

    for profile_name, data in report.profiles.items():
        lines.append(f"### {profile_name}")
        lines.append(f"- Best overall: {data.get('best_overall_model') or 'N/A'}")
        lines.append(f"- Best JSON: {data.get('best_json_model') or 'N/A'}")
        lines.append(f"- Fastest: {data.get('fastest_model') or 'N/A'}")
        lines.append(f"- Most stable: {data.get('most_stable_model') or 'N/A'}")
        models = data.get("models", [])
        if models:
            lines.extend(["", "| Model | Score | JSON Valid Rate | Avg ms |", "| --- | --- | --- | --- |"])
            for m in models:
                lines.append(
                    f"| {m.get('model', '')} | {m.get('overall_score', 0):.4f} | "
                    f"{m.get('json_valid_rate', 0):.2f} | {m.get('average_response_ms', 0):.0f} |"
                )
        lines.append("")

    if report.errors:
        lines.append("## Errors")
        for error in report.errors:
            lines.append(f"- {error}")
        lines.append("")

    lines.append("## Limitations")
    lines.append("- Benchmark results depend on calibration fixture content and size.")
    lines.append("- Local benchmarks are practical estimates, not academic measurements.")
    lines.append("- Cold-start and system load can affect per-model response times.")
    lines.append("")

    return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now().isoformat()
