"""Local model benchmark runner for comparing Ollama models."""

from __future__ import annotations

import json
import time
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governor.adaptive_limits import (
    AdaptiveLimitsConfig,
    load_adaptive_limits_config,
)
from governor.json_guard import JSONGuardResult, guard_json
from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory
from governor.model_profiles import (
    DEFAULT_PROMPT_VERSION,
    DEFAULT_RECOMMENDED_MAX_CHARS,
    ModelProfileEvent,
    ModelProfileStore,
)
from governor.ollama_client import OllamaClient, OllamaConfig, OllamaError, load_ollama_config
from governor.prompt_manager import (
    PromptSelection,
    render_managed_prompt,
    select_prompt,
)
from governor.prompt_renderer import TASK_PROMPT_FILES
from governor.profiles import validate_profile_name
from governor.task_runner import read_text_limited, resolve_task_file


FILE_ANALYSIS_SCHEMA = "file_analysis.schema.json"
DEFAULT_BENCHMARK_OUTPUT_DIR = Path("reports") / "benchmarks"
DEFAULT_MAX_TASKS = 5


@dataclass(frozen=True)
class BenchmarkTaskResult:
    model: str
    file_path: str
    task_type: str
    status: str
    json_valid: bool
    json_repaired: bool
    truncated: bool
    response_time_ms: float | None
    input_chars: int
    output_chars: int
    prompt_version: str
    raw_response: str
    errors: list[str]


@dataclass
class ModelBenchmarkStats:
    model: str = ""
    provider: str = "ollama"
    tasks_attempted: int = 0
    tasks_completed: int = 0
    json_valid: int = 0
    json_repaired: int = 0
    json_failed: int = 0
    model_failed: int = 0
    read_failed: int = 0
    truncated: int = 0
    average_response_ms: float = 0.0
    median_response_ms: float = 0.0
    min_response_ms: float = 0.0
    max_response_ms: float = 0.0
    average_input_chars: float = 0.0
    average_output_chars: float = 0.0
    success_rate: float = 0.0
    json_valid_rate: float = 0.0
    json_repair_rate: float = 0.0
    json_fail_rate: float = 0.0
    model_fail_rate: float = 0.0
    truncation_rate: float = 0.0
    recommended_max_chars: int = DEFAULT_RECOMMENDED_MAX_CHARS
    recommended_prompt_version: str = DEFAULT_PROMPT_VERSION
    overall_score: float = 0.0
    _response_times: list[float] = field(default_factory=list)
    _input_chars_list: list[int] = field(default_factory=list)
    _output_chars_list: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "tasks_attempted": self.tasks_attempted,
            "tasks_completed": self.tasks_completed,
            "json_valid": self.json_valid,
            "json_repaired": self.json_repaired,
            "json_failed": self.json_failed,
            "model_failed": self.model_failed,
            "read_failed": self.read_failed,
            "truncated": self.truncated,
            "average_response_ms": self.average_response_ms,
            "median_response_ms": self.median_response_ms,
            "min_response_ms": self.min_response_ms,
            "max_response_ms": self.max_response_ms,
            "average_input_chars": self.average_input_chars,
            "average_output_chars": self.average_output_chars,
            "success_rate": self.success_rate,
            "json_valid_rate": self.json_valid_rate,
            "json_repair_rate": self.json_repair_rate,
            "json_fail_rate": self.json_fail_rate,
            "model_fail_rate": self.model_fail_rate,
            "truncation_rate": self.truncation_rate,
            "recommended_max_chars": self.recommended_max_chars,
            "recommended_prompt_version": self.recommended_prompt_version,
            "overall_score": self.overall_score,
        }


@dataclass(frozen=True)
class BenchmarkReport:
    metadata: dict[str, Any]
    summary: dict[str, str | None]
    models: list[dict[str, Any]]
    prompt_versions: list[dict[str, Any]]
    errors: list[str]


@dataclass(frozen=True)
class BenchmarkDryRun:
    models: list[str]
    tasks: list[dict[str, Any]]
    prompt_versions: list[str]
    project_path: str
    max_tasks: int
    output_dir: str
    timeout_seconds: int | None = None
    delay_between_models: int = 0
    estimated_timeout_seconds: int | None = None


def run_benchmark(
    project_path: Path | str,
    *,
    models: list[str],
    max_tasks: int = DEFAULT_MAX_TASKS,
    profile: str = "auto",
    mode: str = "general",
    prompt_versions: list[str] | None = None,
    no_adaptive_limits: bool = False,
    timeout_seconds: int | None = None,
    delay_between_models: int = 0,
    output_dir: Path | str = DEFAULT_BENCHMARK_OUTPUT_DIR,
    dry_run: bool = False,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> BenchmarkReport | BenchmarkDryRun:
    project_root = _resolve_project_root(project_path)
    output_path = Path(output_dir)
    created_at = _utc_now()

    config = client.config if client is not None else load_ollama_config()
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if delay_between_models < 0:
        raise ValueError("delay_between_models must be zero or greater")
    if timeout_seconds is not None:
        config = _config_with_timeout(config, timeout_seconds)

    runner_client = client if client is not None else OllamaClient(config)
    task_memory = memory or SQLiteMemory(DEFAULT_MEMORY_PATH)
    profile_name = validate_profile_name(profile)
    adaptive_config = load_adaptive_limits_config(fallback_default_max_chars=config.max_chars_per_file)
    adaptive_enabled = not no_adaptive_limits and adaptive_config.enabled

    files = _collect_files(project_root, max_tasks)
    if not files:
        return BenchmarkReport(
            metadata={"project_path": str(project_root), "created_at": created_at, "max_tasks": max_tasks, "models": models},
            summary={"best_overall_model": None, "best_json_model": None, "fastest_model": None, "most_stable_model": None},
            models=[],
            prompt_versions=[],
            errors=["no files found in project"],
        )

    versions = _resolve_prompt_versions(prompt_versions)

    if dry_run:
        estimated_timeout_seconds = len(models) * len(versions) * len(files) * config.timeout_seconds
        return BenchmarkDryRun(
            models=list(models),
            tasks=[{"file_path": str(f.relative_to(project_root)), "task_type": _task_type_for_file(f)} for f in files],
            prompt_versions=list(versions),
            project_path=str(project_root),
            max_tasks=max_tasks,
            output_dir=str(output_path),
            timeout_seconds=config.timeout_seconds,
            delay_between_models=delay_between_models,
            estimated_timeout_seconds=estimated_timeout_seconds,
        )

    all_results: list[BenchmarkTaskResult] = []
    errors: list[str] = []

    for model_index, model_name in enumerate(models):
        if model_index > 0 and delay_between_models > 0:
            time.sleep(delay_between_models)
        if client is not None:
            bench_client = client
        else:
            model_config = _config_for_model(config, model_name)
            bench_client = OllamaClient(model_config)
        try:
            bench_client.check_ollama_available()
        except OllamaError as exc:
            errors.append(f"model {model_name}: Ollama not available: {exc}")
            continue

        for version in versions:
            for file_path in files:
                try:
                    result = _run_benchmark_task(
                        project_root=project_root,
                        file_path=file_path,
                        model_name=model_name,
                        profile_name=profile_name,
                        prompt_version=version,
                        client=bench_client,
                        task_memory=task_memory,
                        adaptive_config=adaptive_config,
                        adaptive_enabled=adaptive_enabled,
                    )
                    all_results.append(result)
                except Exception as exc:
                    errors.append(f"model={model_name} file={file_path}: {exc}")

    stats_by_model = _aggregate_stats(all_results, models)
    summary = _compute_summary(stats_by_model)
    _update_model_profiles(all_results, task_memory, project_root, profile_name, adaptive_enabled)

    report = BenchmarkReport(
        metadata={"project_path": str(project_root), "created_at": created_at, "max_tasks": max_tasks, "models": models},
        summary=summary,
        models=[s.to_dict() for s in stats_by_model],
        prompt_versions=[{"version": v} for v in versions],
        errors=errors,
    )

    _write_benchmark_reports(report, output_path)
    return report


def benchmark_dry_run(project_path: Path | str, *, models: list[str], max_tasks: int = DEFAULT_MAX_TASKS) -> BenchmarkDryRun:
    return run_benchmark(project_path, models=models, max_tasks=max_tasks, dry_run=True)  # type: ignore[return-value]


def compute_scores(stats_list: list[ModelBenchmarkStats]) -> None:
    if not stats_list:
        return
    all_times = [s.average_response_ms for s in stats_list if s.tasks_completed > 0]
    min_time = min(all_times) if all_times else 1
    max_time = max(all_times) if all_times else 1

    for stats in stats_list:
        if stats.tasks_attempted == 0 or stats.tasks_completed == 0:
            stats.overall_score = 0.0
            continue
        speed_score = _normalize_speed(stats.average_response_ms, min_time, max_time) if all_times and stats.tasks_completed > 0 else 0.0
        low_repair_score = 1.0 - stats.json_repair_rate
        stats.overall_score = round(
            stats.json_valid_rate * 0.45
            + stats.success_rate * 0.25
            + speed_score * 0.20
            + low_repair_score * 0.10,
            4,
        )


def _run_benchmark_task(
    *,
    project_root: Path,
    file_path: Path,
    model_name: str,
    profile_name: str,
    prompt_version: str,
    client: OllamaClient,
    task_memory: SQLiteMemory,
    adaptive_config: AdaptiveLimitsConfig,
    adaptive_enabled: bool,
) -> BenchmarkTaskResult:
    task_type = _task_type_for_file(file_path)
    prompt_selection = select_prompt(
        model=model_name,
        task_type=task_type,
        profile=profile_name,
        store=task_memory.model_profile_store(),
        manual_prompt_version=prompt_version,
    )

    relative_path = str(file_path.relative_to(project_root))
    max_chars = adaptive_config.default_max_chars

    resolved = resolve_task_file(project_root, relative_path)
    read_result = read_text_limited(resolved, max_chars)

    prompt = render_managed_prompt(
        selection=prompt_selection,
        file_path=relative_path,
        profile=profile_name,
        task_type=task_type,
        file_content=read_result.content,
    )

    started_at = time.perf_counter()
    raw_response = ""
    errors: list[str] = []

    try:
        raw_response = client.analyze_text_with_model(prompt, read_result.content, max_chars=max_chars)
    except OllamaError as exc:
        elapsed = (time.perf_counter() - started_at) * 1000
        return BenchmarkTaskResult(
            model=model_name,
            file_path=relative_path,
            task_type=task_type,
            status="failed_model",
            json_valid=False,
            json_repaired=False,
            truncated=read_result.truncated,
            response_time_ms=elapsed,
            input_chars=len(read_result.content),
            output_chars=0,
            prompt_version=prompt_selection.version,
            raw_response="",
            errors=[str(exc)],
        )

    elapsed = (time.perf_counter() - started_at) * 1000
    guarded = guard_json(raw_response, FILE_ANALYSIS_SCHEMA)
    status = _benchmark_status(guarded)

    result = BenchmarkTaskResult(
        model=model_name,
        file_path=relative_path,
        task_type=task_type,
        status=status,
        json_valid=guarded.valid,
        json_repaired=guarded.repaired,
        truncated=read_result.truncated,
        response_time_ms=elapsed,
        input_chars=len(read_result.content),
        output_chars=len(raw_response),
        prompt_version=prompt_selection.version,
        raw_response=raw_response,
        errors=guarded.errors if not guarded.valid else [],
    )

    _save_benchmark_profile(result, task_memory, project_root, profile_name)
    return result


def _benchmark_status(guarded: JSONGuardResult) -> str:
    if guarded.valid:
        return "completed"
    if guarded.data is not None:
        return "failed_json"
    return "failed_json"


def _aggregate_stats(results: list[BenchmarkTaskResult], models: list[str]) -> list[ModelBenchmarkStats]:
    by_model: dict[str, list[BenchmarkTaskResult]] = {m: [] for m in models}
    for r in results:
        if r.model in by_model:
            by_model[r.model].append(r)

    stats_list: list[ModelBenchmarkStats] = []
    for model_name in models:
        entries = by_model[model_name]
        if not entries:
            stats = ModelBenchmarkStats(model=model_name)
            stats_list.append(stats)
            continue

        stats = ModelBenchmarkStats(model=model_name)
        stats.tasks_attempted = len(entries)
        response_times: list[float] = []
        input_chars: list[int] = []
        output_chars: list[int] = []

        for r in entries:
            if r.status == "completed":
                stats.tasks_completed += 1
            if r.json_valid:
                stats.json_valid += 1
            if r.json_repaired:
                stats.json_repaired += 1
            if r.status == "failed_json":
                stats.json_failed += 1
            if r.status == "failed_model":
                stats.model_failed += 1
            if r.status == "failed_read":
                stats.read_failed += 1
            if r.truncated:
                stats.truncated += 1
            if r.response_time_ms is not None:
                response_times.append(r.response_time_ms)
            input_chars.append(r.input_chars)
            output_chars.append(r.output_chars)

        total = stats.tasks_attempted
        stats.success_rate = round(stats.tasks_completed / total, 4) if total > 0 else 0.0
        stats.json_valid_rate = round(stats.json_valid / total, 4) if total > 0 else 0.0
        stats.json_repair_rate = round(stats.json_repaired / total, 4) if total > 0 else 0.0
        stats.json_fail_rate = round(stats.json_failed / total, 4) if total > 0 else 0.0
        stats.model_fail_rate = round(stats.model_failed / total, 4) if total > 0 else 0.0
        stats.truncation_rate = round(stats.truncated / total, 4) if total > 0 else 0.0

        if response_times:
            stats.average_response_ms = round(statistics.mean(response_times), 1)
            stats.median_response_ms = round(statistics.median(response_times), 1)
            stats.min_response_ms = round(min(response_times), 1)
            stats.max_response_ms = round(max(response_times), 1)
        if input_chars:
            stats.average_input_chars = round(statistics.mean(input_chars), 1)
        if output_chars:
            stats.average_output_chars = round(statistics.mean(output_chars), 1)

        stats.recommended_max_chars = _default_recommended_max_chars(stats)
        stats.recommended_prompt_version = _best_version_for_results(entries)

        stats._response_times = response_times
        stats._input_chars_list = input_chars
        stats._output_chars_list = output_chars

        stats_list.append(stats)

    compute_scores(stats_list)
    return stats_list


def _compute_summary(stats_list: list[ModelBenchmarkStats]) -> dict[str, str | None]:
    scored = [s for s in stats_list if s.tasks_attempted > 0]
    if not scored:
        return {"best_overall_model": None, "best_json_model": None, "fastest_model": None, "most_stable_model": None}

    best_overall = max(scored, key=lambda s: s.overall_score)
    best_json = max(scored, key=lambda s: s.json_valid_rate)
    fastest = min(
        [s for s in scored if s.average_response_ms > 0],
        key=lambda s: s.average_response_ms,
        default=scored[0],
    )
    most_stable = min(scored, key=lambda s: (s.model_fail_rate, s.json_fail_rate))

    return {
        "best_overall_model": best_overall.model,
        "best_json_model": best_json.model,
        "fastest_model": fastest.model,
        "most_stable_model": most_stable.model,
    }


def _update_model_profiles(
    results: list[BenchmarkTaskResult],
    memory: SQLiteMemory,
    project_root: Path,
    profile_name: str,
    adaptive_enabled: bool,
) -> None:
    profile_store = memory.model_profile_store()
    for r in results:
        profile_store.record_task_result(
            ModelProfileEvent(
                model=r.model,
                task_type=r.task_type,
                profile=profile_name,
                prompt_version=r.prompt_version,
                status=r.status,
                json_valid=r.json_valid,
                json_repaired=r.json_repaired,
                truncated=r.truncated,
                response_time_ms=r.response_time_ms,
                input_chars=r.input_chars,
                output_chars=r.output_chars,
            )
        )


def _write_benchmark_reports(report: BenchmarkReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"benchmark-{stamp}.json"
    md_path = output_dir / f"benchmark-{stamp}.md"

    data = {
        "metadata": report.metadata,
        "summary": report.summary,
        "models": report.models,
        "prompt_versions": report.prompt_versions,
        "errors": report.errors,
    }
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(_render_benchmark_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_benchmark_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# LocalScope Model Benchmark",
        "",
        f"**Project:** {report.metadata.get('project_path', '')}",
        f"**Generated:** {report.metadata.get('created_at', '')}",
        f"**Max tasks:** {report.metadata.get('max_tasks', 0)}",
        "",
        "## Summary",
        f"- Best overall model: {report.summary.get('best_overall_model') or 'N/A'}",
        f"- Best JSON valid model: {report.summary.get('best_json_model') or 'N/A'}",
        f"- Fastest model: {report.summary.get('fastest_model') or 'N/A'}",
        f"- Most stable model: {report.summary.get('most_stable_model') or 'N/A'}",
        "",
        "## Models",
    ]

    for model in report.models:
        lines.extend([
            f"### {model.get('model', '')} ({model.get('provider', '')})",
            f"**Overall score:** {model.get('overall_score', 0)}",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Tasks attempted | {model.get('tasks_attempted', 0)} |",
            f"| Tasks completed | {model.get('tasks_completed', 0)} |",
            f"| JSON valid | {model.get('json_valid', 0)} |",
            f"| JSON repaired | {model.get('json_repaired', 0)} |",
            f"| JSON failed | {model.get('json_failed', 0)} |",
            f"| Model failed | {model.get('model_failed', 0)} |",
            f"| Read failed | {model.get('read_failed', 0)} |",
            f"| Truncated | {model.get('truncated', 0)} |",
            f"| Avg response (ms) | {model.get('average_response_ms', 0)} |",
            f"| Median response (ms) | {model.get('median_response_ms', 0)} |",
            f"| Min response (ms) | {model.get('min_response_ms', 0)} |",
            f"| Max response (ms) | {model.get('max_response_ms', 0)} |",
            f"| Avg input chars | {model.get('average_input_chars', 0)} |",
            f"| Avg output chars | {model.get('average_output_chars', 0)} |",
            f"| Success rate | {model.get('success_rate', 0)} |",
            f"| JSON valid rate | {model.get('json_valid_rate', 0)} |",
            f"| JSON repair rate | {model.get('json_repair_rate', 0)} |",
            f"| JSON fail rate | {model.get('json_fail_rate', 0)} |",
            f"| Model fail rate | {model.get('model_fail_rate', 0)} |",
            f"| Truncation rate | {model.get('truncation_rate', 0)} |",
            f"| Recommended max chars | {model.get('recommended_max_chars', 0)} |",
            f"| Recommended prompt version | {model.get('recommended_prompt_version', '')} |",
            "",
        ])

    if report.prompt_versions:
        lines.append("## Prompt versions used")
        for pv in report.prompt_versions:
            lines.append(f"- {pv.get('version', '')}")
        lines.append("")

    if report.errors:
        lines.append("## Errors")
        for error in report.errors:
            lines.append(f"- {error}")
        lines.append("")

    lines.append("## Limitations")
    lines.append("- Only Ollama provider is supported.")
    lines.append("- Results depend on the specific fixture/project used.")
    lines.append("- Scoring uses a simple deterministic formula.")
    lines.append("")

    return "\n".join(lines)


def _normalize_speed(avg_ms: float, min_ms: float, max_ms: float) -> float:
    if max_ms <= min_ms:
        return 1.0
    if avg_ms <= 0:
        return 0.0
    return round(1.0 - (avg_ms - min_ms) / (max_ms - min_ms), 4)


def _default_recommended_max_chars(stats: ModelBenchmarkStats) -> int:
    if stats.json_fail_rate > 0.30:
        return max(2000, int(DEFAULT_RECOMMENDED_MAX_CHARS * 0.75))
    if stats.json_valid_rate > 0.85:
        return min(24000, DEFAULT_RECOMMENDED_MAX_CHARS + 500)
    return DEFAULT_RECOMMENDED_MAX_CHARS


def _best_version_for_results(results: list[BenchmarkTaskResult]) -> str:
    by_version: dict[str, list[BenchmarkTaskResult]] = {}
    for r in results:
        by_version.setdefault(r.prompt_version, []).append(r)
    best_version = DEFAULT_PROMPT_VERSION
    best_rate = -1.0
    for version, entries in by_version.items():
        if not entries:
            continue
        valid_rate = sum(1 for e in entries if e.json_valid) / len(entries)
        if valid_rate > best_rate:
            best_rate = valid_rate
            best_version = version
    return best_version


def _collect_files(project_root: Path, max_tasks: int) -> list[Path]:
    files: list[Path] = []
    for file_path in sorted(project_root.rglob("*")):
        if file_path.is_file() and _is_relevant_file(file_path):
            files.append(file_path)
        if len(files) >= max_tasks:
            break
    return files[:max_tasks]


def _is_relevant_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in {".py", ".js", ".ts", ".php", ".java", ".json", ".yaml", ".yml", ".md", ".txt", ".cfg", ".conf", ".ini", ".toml", ".xml", ".html", ".css", ".sh", ".dockerfile"}


def _task_type_for_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".py", ".js", ".ts", ".php", ".java", ".sh"}:
        return "inspect_code_file"
    if ext in {".json", ".yaml", ".yml", ".cfg", ".conf", ".ini", ".toml", ".xml", ".dockerfile"}:
        return "inspect_config_file"
    if ext in {".md", ".txt"}:
        return "inspect_documentation_file"
    return "inspect_unknown_file"


def _resolve_prompt_versions(requested: list[str] | None) -> list[str]:
    if not requested:
        return [DEFAULT_PROMPT_VERSION]
    normalized = []
    for v in requested:
        v = v.strip()
        if v and v not in normalized:
            normalized.append(v)
    return normalized or [DEFAULT_PROMPT_VERSION]


def _resolve_project_root(project_path: Path | str) -> Path:
    root = Path(project_path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"project path is not a directory: {root}")
    return root


def _config_with_timeout(config: OllamaConfig, timeout_seconds: int) -> OllamaConfig:
    return OllamaConfig(
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        timeout_seconds=timeout_seconds,
        max_chars_per_file=config.max_chars_per_file,
    )


def _config_for_model(config: OllamaConfig, model_name: str) -> OllamaConfig:
    return OllamaConfig(
        base_url=config.base_url,
        model=model_name,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        max_chars_per_file=config.max_chars_per_file,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_benchmark_profile(
    result: BenchmarkTaskResult,
    memory: SQLiteMemory,
    project_root: Path,
    profile_name: str,
) -> None:
    profile_store = memory.model_profile_store()
    profile_store.record_task_result(
        ModelProfileEvent(
            model=result.model,
            task_type=result.task_type,
            profile=profile_name,
            prompt_version=result.prompt_version,
            status=result.status,
            json_valid=result.json_valid,
            json_repaired=result.json_repaired,
            truncated=result.truncated,
            response_time_ms=result.response_time_ms,
            input_chars=result.input_chars,
            output_chars=result.output_chars,
        )
    )
