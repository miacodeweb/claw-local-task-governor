"""Read-only Task Runner v1 for pending microtasks."""

from __future__ import annotations

import json
import time
import inspect
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governor.adaptive_limits import (
    AdaptiveLimitDecision,
    AdaptiveLimitsConfig,
    load_adaptive_limits_config,
    resolve_effective_max_chars,
)
from governor.json_guard import JSONGuardResult, guard_json
from governor.logging_manager import get_log_manager
from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory
from governor.model_resolver import resolve_model
from governor.ollama_client import OllamaClient, OllamaError, OllamaConfig, load_ollama_config
from governor.prompt_manager import (
    PromptSelection,
    render_managed_prompt,
    select_prompt,
)
from governor.profiles import validate_profile_name
from governor.prompt_renderer import PromptRenderError


DEFAULT_OUTPUT_DIR = Path("reports")
TASKS_FILENAME = "tasks.json"
TASK_RESULTS_FILENAME = "task_results.json"
FILE_ANALYSIS_SCHEMA = "file_analysis.schema.json"
PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class ReadFileResult:
    content: str
    truncated: bool


@dataclass(frozen=True)
class DryRunTask:
    task_id: str
    file_path: str
    task_type: str
    profile: str
    valid_path: bool
    truncated: bool
    prompt_preview: str
    errors: list[str]
    max_chars_used: int = 0
    adaptive_limits_enabled: bool = False
    adaptive_reason: str = ""
    prompt_version: str = PROMPT_VERSION
    prompt_selected_reason: str = ""


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    file_path: str
    file_hash: str
    task_type: str
    profile: str
    status: str
    json_valid: bool
    json_repaired: bool
    truncated: bool
    model: str
    raw_response: str
    result: Any
    errors: list[str]
    created_at: str
    project_path: str = ""
    risk: str = "none"
    max_chars_used: int = 0
    adaptive_limits_enabled: bool = False
    adaptive_reason: str = ""
    prompt_version: str = PROMPT_VERSION
    prompt_selected_reason: str = ""


@dataclass(frozen=True)
class TaskRunSummary:
    project_path: str
    generated_at: str
    max_tasks: int
    tasks_requested: int
    tasks_loaded: int
    tasks_selected: int
    tasks_processed: int
    tasks_completed: int
    tasks_failed: int
    failed_json: int
    failed_model: int
    failed_read: int
    json_repaired: int
    output_path: str
    dry_run: bool
    results: list[TaskRunResult]
    dry_run_tasks: list[DryRunTask]
    tasks_new: int = 0
    tasks_reused: int = 0
    model_used: str = ""
    benchmark_source: str = ""
    prompt_version_used: str = ""
    max_chars_used: int = 0
    adaptive_limits_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "generated_at": self.generated_at,
            "max_tasks": self.max_tasks,
            "tasks_requested": self.tasks_requested,
            "tasks_loaded": self.tasks_loaded,
            "tasks_selected": self.tasks_selected,
            "tasks_processed": self.tasks_processed,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "failed_json": self.failed_json,
            "failed_model": self.failed_model,
            "failed_read": self.failed_read,
            "json_repaired": self.json_repaired,
            "output_path": self.output_path,
            "dry_run": self.dry_run,
            "tasks_new": self.tasks_new,
            "tasks_reused": self.tasks_reused,
            "results": [asdict(result) for result in self.results],
            "dry_run_tasks": [asdict(task) for task in self.dry_run_tasks],
            "model_used": self.model_used,
            "benchmark_source": self.benchmark_source,
            "prompt_version_used": self.prompt_version_used,
            "max_chars_used": self.max_chars_used,
            "adaptive_limits_enabled": self.adaptive_limits_enabled,
        }


def run_pending_tasks(
    project_path: Path | str,
    *,
    max_tasks: int,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: OllamaClient | None = None,
    dry_run: bool = False,
    memory: SQLiteMemory | None = None,
    no_memory: bool = False,
    profile_override: str | None = "auto",
    no_adaptive_limits: bool = False,
    prompt_version: str | None = None,
    model_override: str | None = None,
    use_benchmark_recommendations: bool = False,
) -> TaskRunSummary:
    """Run a limited number of pending tasks from tasks.json."""
    if max_tasks < 1:
        raise ValueError("max_tasks must be greater than 0")

    project_root = _resolve_project_root(project_path)
    output_path = Path(output_dir)
    tasks_path = output_path / TASKS_FILENAME
    tasks_data = _load_json_file(tasks_path)
    pending_tasks = [task for task in tasks_data.get("tasks", []) if task.get("status") == "pending"]
    selected_tasks = pending_tasks[:max_tasks]
    selected_tasks = apply_profile_override(selected_tasks, profile_override)
    config = client.config if client is not None else load_ollama_config()
    adaptive_config = load_adaptive_limits_config(fallback_default_max_chars=config.max_chars_per_file)
    adaptive_enabled = not no_adaptive_limits and adaptive_config.enabled
    task_memory = None if dry_run and not adaptive_enabled else (memory or SQLiteMemory(DEFAULT_MEMORY_PATH))

    from governor.model_recommendations import get_model_recommendations

    rec = get_model_recommendations(memory=task_memory, latest_benchmark=True) if use_benchmark_recommendations else None

    resolved_obj = resolve_model(
        model_override=model_override,
        use_benchmark_recommendations=use_benchmark_recommendations,
        config_model=config.model,
        recommendation=rec,
    )
    resolved_model = resolved_obj.model
    benchmark_source = resolved_obj.benchmark_source or resolved_obj.source
    resolved_config = _config_for_model(config, resolved_model)

    runner_client = client if client is not None else OllamaClient(resolved_config)
    created_at = datetime.now(timezone.utc).isoformat()

    if dry_run:
        dry_tasks = []
        for task in selected_tasks:
            prompt_selection = resolve_task_prompt_selection(
                task,
                model=resolved_model,
                memory=task_memory,
                manual_prompt_version=prompt_version,
            )
            dry_tasks.append(
                inspect_task_for_dry_run(
                    task,
                    project_root=project_root,
                    limit_decision=resolve_task_limit(
                        task,
                        model=resolved_model,
                        fixed_max_chars=config.max_chars_per_file,
                        memory=task_memory,
                        adaptive_config=adaptive_config,
                        adaptive_enabled=adaptive_enabled,
                        prompt_version=prompt_selection.version,
                    ),
                    prompt_selection=prompt_selection,
                )
            )
            return _build_summary(
                project_root=project_root,
                max_tasks=max_tasks,
                tasks_loaded=len(tasks_data.get("tasks", [])),
                selected_count=len(selected_tasks),
                output_path=output_path / TASK_RESULTS_FILENAME,
                dry_run=True,
                results=[],
                dry_run_tasks=dry_tasks,
                generated_at=created_at,
                model_used=resolved_model,
                benchmark_source=benchmark_source,
                adaptive_enabled=adaptive_enabled,
            )

    results: list[TaskRunResult] = []
    for task in selected_tasks:
        prompt_selection = resolve_task_prompt_selection(
            task,
            model=resolved_model,
            memory=task_memory,
            manual_prompt_version=prompt_version,
        )
        limit_decision = resolve_task_limit(
            task,
            model=resolved_model,
            fixed_max_chars=config.max_chars_per_file,
            memory=task_memory,
            adaptive_config=adaptive_config,
            adaptive_enabled=adaptive_enabled,
            prompt_version=prompt_selection.version,
        )
        results.append(
            run_single_task(
                task,
                project_root=project_root,
                client=runner_client,
                limit_decision=limit_decision,
                prompt_selection=prompt_selection,
                model=config.model,
                memory=task_memory,
                use_memory_cache=not no_memory,
            )
        )

    summary = _build_summary(
        project_root=project_root,
        max_tasks=max_tasks,
        tasks_loaded=len(tasks_data.get("tasks", [])),
        selected_count=len(selected_tasks),
        output_path=output_path / TASK_RESULTS_FILENAME,
        dry_run=False,
        results=results,
        dry_run_tasks=[],
        generated_at=created_at,
        model_used=resolved_model,
        benchmark_source=benchmark_source,
        adaptive_enabled=adaptive_enabled,
    )
    write_task_results(summary, output_path)
    return summary


def run_single_task(
    task: dict[str, Any],
    *,
    project_root: Path,
    client: OllamaClient,
    limit_decision: AdaptiveLimitDecision,
    prompt_selection: PromptSelection,
    model: str,
    memory: SQLiteMemory | None = None,
    use_memory_cache: bool = True,
) -> TaskRunResult:
    created_at = datetime.now(timezone.utc).isoformat()
    raw_response = ""
    truncated = False
    input_chars = 0
    output_chars = 0
    response_time_seconds: float | None = None
    started_at: float | None = None
    max_chars = limit_decision.effective_max_chars

    logger = get_log_manager()
    task_id = str(task["task_id"])
    task_type = str(task["task_type"])
    rel_path = str(task["file_path"])

    logger.task_started(
        task_id=task_id,
        task_type=task_type,
        file_path=rel_path,
        model=model,
        prompt_version=prompt_selection.version,
        max_chars_used=max_chars,
        adaptive_enabled=limit_decision.enabled,
    )

    try:
        if memory is not None and use_memory_cache:
            reusable = memory.find_reusable_result(
                project_path=str(project_root),
                file_path=str(task["file_path"]),
                file_hash=str(task["file_hash"]),
                task_type=str(task["task_type"]),
                model=model,
                prompt_version=prompt_selection.version,
            )
            if reusable is not None:
                return _result_from_reusable(task, reusable, created_at)

        file_path = resolve_task_file(project_root, str(task["file_path"]))
        read_result = read_text_limited(file_path, max_chars)
        truncated = read_result.truncated
        input_chars = len(read_result.content)
        prompt = render_task_prompt(task, read_result.content, prompt_selection)
        started_at = time.perf_counter()
        raw_response = analyze_text_with_limit(client, prompt, read_result.content, max_chars)
        response_time_seconds = time.perf_counter() - started_at
        output_chars = len(raw_response)
        guarded = guard_json(raw_response, FILE_ANALYSIS_SCHEMA)
        result = _result_from_guard(
            task,
            guarded,
            raw_response,
            truncated,
            model,
            created_at,
            limit_decision,
            prompt_selection,
        )
        save_result_to_memory(
            memory,
            result,
            project_root=project_root,
            response_time_seconds=response_time_seconds,
            current_max_chars=max_chars,
            input_chars=input_chars,
            output_chars=output_chars,
        )
        logger.task_completed(
            task_id=task_id,
            task_type=task_type,
            file_path=rel_path,
            model=model,
            duration_ms=int((response_time_seconds or 0) * 1000),
            json_valid=guarded.valid,
            json_repaired=guarded.repaired,
            reused=False,
        )
        return result
    except (OSError, UnicodeDecodeError, ValueError, KeyError) as error:
        result = _failed_result(
            task,
            "failed_read",
            [str(error)],
            raw_response,
            truncated,
            model,
            created_at,
            limit_decision,
            prompt_selection,
        )
        save_result_to_memory(
            memory,
            result,
            project_root=project_root,
            current_max_chars=max_chars,
            input_chars=input_chars,
            output_chars=output_chars,
        )
        logger.task_failed(
            task_id=task_id,
            task_type=task_type,
            file_path=rel_path,
            model=model,
            error_message=str(error),
            reason="failed_read",
        )
        logger.log_error(
            error_type=type(error).__name__,
            error_message=str(error),
            command="run-tasks",
            task_id=task_id,
            file_path=rel_path,
            model=model,
        )
        return result
    except PromptRenderError as error:
        result = _failed_result(
            task,
            "failed_read",
            [str(error)],
            raw_response,
            truncated,
            model,
            created_at,
            limit_decision,
            prompt_selection,
        )
        save_result_to_memory(
            memory,
            result,
            project_root=project_root,
            current_max_chars=max_chars,
            input_chars=input_chars,
            output_chars=output_chars,
        )
        logger.task_failed(
            task_id=task_id,
            task_type=task_type,
            file_path=rel_path,
            model=model,
            error_message=str(error),
            reason="prompt_render_error",
        )
        logger.log_error(
            error_type="PromptRenderError",
            error_message=str(error),
            command="run-tasks",
            task_id=task_id,
            file_path=rel_path,
            model=model,
        )
        return result
    except OllamaError as error:
        if started_at is not None:
            response_time_seconds = time.perf_counter() - started_at
        result = _failed_result(
            task,
            "failed_model",
            [str(error)],
            raw_response,
            truncated,
            model,
            created_at,
            limit_decision,
            prompt_selection,
        )
        save_result_to_memory(
            memory,
            result,
            project_root=project_root,
            response_time_seconds=response_time_seconds,
            current_max_chars=max_chars,
            input_chars=input_chars,
            output_chars=output_chars,
        )
        logger.task_failed(
            task_id=task_id,
            task_type=task_type,
            file_path=rel_path,
            model=model,
            error_message=str(error),
            reason="failed_model",
        )
        logger.log_error(
            error_type=type(error).__name__,
            error_message=str(error),
            command="run-tasks",
            task_id=task_id,
            file_path=rel_path,
            model=model,
        )
        return result


def inspect_task_for_dry_run(
    task: dict[str, Any],
    *,
    project_root: Path,
    limit_decision: AdaptiveLimitDecision,
    prompt_selection: PromptSelection,
) -> DryRunTask:
    errors: list[str] = []
    prompt_preview = ""
    truncated = False
    valid_path = False
    max_chars = limit_decision.effective_max_chars

    try:
        file_path = resolve_task_file(project_root, str(task["file_path"]))
        valid_path = True
        read_result = read_text_limited(file_path, max_chars)
        truncated = read_result.truncated
        prompt = render_task_prompt(task, read_result.content, prompt_selection)
        prompt_preview = summarize_prompt(prompt)
    except (OSError, UnicodeDecodeError, ValueError, KeyError, PromptRenderError) as error:
        errors.append(str(error))

    return DryRunTask(
        task_id=str(task.get("task_id", "")),
        file_path=str(task.get("file_path", "")),
        task_type=str(task.get("task_type", "inspect_unknown_file")),
        profile=str(task.get("profile", "general")),
        valid_path=valid_path,
        truncated=truncated,
        prompt_preview=prompt_preview,
        errors=errors,
        max_chars_used=max_chars,
        adaptive_limits_enabled=limit_decision.enabled,
        adaptive_reason=limit_decision.reason,
        prompt_version=prompt_selection.version,
        prompt_selected_reason=prompt_selection.reason,
    )


def render_task_prompt(
    task: dict[str, Any],
    file_content: str,
    prompt_selection: PromptSelection,
) -> str:
    return render_managed_prompt(
        selection=prompt_selection,
        file_path=str(task["file_path"]),
        profile=str(task.get("profile", "general")),
        task_type=str(task.get("task_type", "inspect_unknown_file")),
        file_content=file_content,
        task_id=str(task.get("task_id", "")),
    )


def resolve_task_prompt_selection(
    task: dict[str, Any],
    *,
    model: str,
    memory: SQLiteMemory | None,
    manual_prompt_version: str | None,
) -> PromptSelection:
    return select_prompt(
        model=model,
        task_type=str(task.get("task_type", "inspect_unknown_file")),
        profile=str(task.get("profile", "general")),
        store=None if memory is None else memory.model_profile_store(),
        manual_prompt_version=manual_prompt_version,
    )


def resolve_task_limit(
    task: dict[str, Any],
    *,
    model: str,
    fixed_max_chars: int,
    memory: SQLiteMemory | None,
    adaptive_config: AdaptiveLimitsConfig,
    adaptive_enabled: bool,
    prompt_version: str = PROMPT_VERSION,
) -> AdaptiveLimitDecision:
    return resolve_effective_max_chars(
        model=model,
        task_type=str(task.get("task_type", "inspect_unknown_file")),
        profile=str(task.get("profile", "general")),
        prompt_version=prompt_version,
        store=None if memory is None else memory.model_profile_store(),
        config=adaptive_config,
        fixed_max_chars=fixed_max_chars,
        enabled=adaptive_enabled,
    )


def analyze_text_with_limit(client: OllamaClient, prompt: str, text: str, max_chars: int) -> str:
    analyzer = client.analyze_text_with_model
    try:
        signature = inspect.signature(analyzer)
    except (TypeError, ValueError):
        return analyzer(prompt, text)
    if "max_chars" in signature.parameters:
        return analyzer(prompt, text, max_chars=max_chars)
    return analyzer(prompt, text)


def apply_profile_override(tasks: list[dict[str, Any]], profile_override: str | None) -> list[dict[str, Any]]:
    profile_name = validate_profile_name(profile_override or "auto")
    if profile_name == "auto":
        return tasks
    overridden = []
    for task in tasks:
        item = dict(task)
        item["profile"] = profile_name
        overridden.append(item)
    return overridden


def resolve_task_file(project_root: Path, task_file_path: str) -> Path:
    file_path = (project_root / task_file_path).resolve(strict=True)
    if not _is_relative_to(file_path, project_root):
        raise ValueError(f"task file path escapes project root: {task_file_path}")
    if not file_path.is_file():
        raise ValueError(f"task path is not a file: {task_file_path}")
    return file_path


def read_text_limited(path: Path, max_chars: int) -> ReadFileResult:
    if max_chars < 1:
        raise ValueError("max_chars must be greater than 0")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        content = handle.read(max_chars + 1)
    truncated = len(content) > max_chars
    return ReadFileResult(content=content[:max_chars], truncated=truncated)


def write_task_results(summary: TaskRunSummary, output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Path:
    output_path = Path(output_dir) / TASK_RESULTS_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    return output_path


def summarize_prompt(prompt: str, max_chars: int = 240) -> str:
    compact = " ".join(prompt.split())
    return compact if len(compact) <= max_chars else compact[: max_chars - 3] + "..."


def save_result_to_memory(
    memory: SQLiteMemory | None,
    result: TaskRunResult,
    *,
    project_root: Path,
    response_time_seconds: float | None = None,
    current_max_chars: int | None = None,
    input_chars: int = 0,
    output_chars: int = 0,
) -> None:
    if memory is None:
        return
    memory.save_task_result(
        project_path=str(project_root),
        project_type=result.profile,
        file_path=result.file_path,
        file_hash=result.file_hash,
        task_id=result.task_id,
        task_type=result.task_type,
        profile=result.profile,
        model=result.model,
        prompt_version=result.prompt_version,
        status=result.status,
        json_valid=result.json_valid,
        json_repaired=result.json_repaired,
        truncated=result.truncated,
        risk=result.risk,
        raw_response=result.raw_response,
        result_json=result.result if isinstance(result.result, dict) else None,
        errors=result.errors,
        created_at=result.created_at,
        response_time_seconds=response_time_seconds,
        current_max_chars=current_max_chars,
        input_chars=input_chars,
        output_chars=output_chars,
    )


def _result_from_guard(
    task: dict[str, Any],
    guarded: JSONGuardResult,
    raw_response: str,
    truncated: bool,
    model: str,
    created_at: str,
    limit_decision: AdaptiveLimitDecision,
    prompt_selection: PromptSelection,
) -> TaskRunResult:
    status = "completed" if guarded.valid else "failed_json"
    data = guarded.data if guarded.valid else None
    risk = data.get("risk", "none") if isinstance(data, dict) else "none"
    return TaskRunResult(
        task_id=str(task["task_id"]),
        file_path=str(task["file_path"]),
        file_hash=str(task["file_hash"]),
        task_type=str(task["task_type"]),
        profile=str(task.get("profile", "general")),
        status=status,
        json_valid=guarded.valid,
        json_repaired=guarded.repaired,
        truncated=truncated,
        model=model,
        raw_response=raw_response,
        result=data,
        errors=guarded.errors,
        created_at=created_at,
        project_path=str(task.get("project_path", "")),
        risk=risk,
        max_chars_used=limit_decision.effective_max_chars,
        adaptive_limits_enabled=limit_decision.enabled,
        adaptive_reason=limit_decision.reason,
        prompt_version=prompt_selection.version,
        prompt_selected_reason=prompt_selection.reason,
    )


def _result_from_reusable(
    task: dict[str, Any],
    reusable: Any,
    created_at: str,
) -> TaskRunResult:
    return TaskRunResult(
        task_id=str(task.get("task_id") or reusable.task_id),
        file_path=str(reusable.file_path),
        file_hash=str(reusable.file_hash),
        task_type=str(reusable.task_type),
        profile=str(reusable.profile),
        status="reused",
        json_valid=reusable.json_valid,
        json_repaired=reusable.json_repaired,
        truncated=reusable.truncated,
        model=str(reusable.model),
        raw_response=str(reusable.raw_response),
        result=reusable.result_json,
        errors=list(reusable.errors),
        created_at=created_at,
        project_path=str(task.get("project_path") or reusable.project_path),
        risk=str(reusable.risk),
        max_chars_used=0,
        adaptive_limits_enabled=False,
        adaptive_reason="reused_from_memory",
        prompt_version=str(reusable.prompt_version),
        prompt_selected_reason="reused_from_memory",
    )


def _failed_result(
    task: dict[str, Any],
    status: str,
    errors: list[str],
    raw_response: str,
    truncated: bool,
    model: str,
    created_at: str,
    limit_decision: AdaptiveLimitDecision,
    prompt_selection: PromptSelection,
) -> TaskRunResult:
    return TaskRunResult(
        task_id=str(task.get("task_id", "")),
        file_path=str(task.get("file_path", "")),
        file_hash=str(task.get("file_hash", "")),
        task_type=str(task.get("task_type", "inspect_unknown_file")),
        profile=str(task.get("profile", "general")),
        status=status,
        json_valid=False,
        json_repaired=False,
        truncated=truncated,
        model=model,
        raw_response=raw_response,
        result=None,
        errors=errors,
        created_at=created_at,
        project_path=str(task.get("project_path", "")),
        max_chars_used=limit_decision.effective_max_chars,
        adaptive_limits_enabled=limit_decision.enabled,
        adaptive_reason=limit_decision.reason,
        prompt_version=prompt_selection.version,
        prompt_selected_reason=prompt_selection.reason,
    )


def _build_summary(
    *,
    project_root: Path,
    max_tasks: int,
    tasks_loaded: int,
    selected_count: int,
    output_path: Path,
    dry_run: bool,
    results: list[TaskRunResult],
    dry_run_tasks: list[DryRunTask],
    generated_at: str,
    model_used: str = "",
    benchmark_source: str = "",
    adaptive_enabled: bool = False,
) -> TaskRunSummary:
    failed_json = sum(1 for result in results if result.status == "failed_json")
    failed_model = sum(1 for result in results if result.status == "failed_model")
    failed_read = sum(1 for result in results if result.status == "failed_read")
    completed = sum(1 for result in results if result.status == "completed")
    reused = sum(1 for result in results if result.status == "reused")
    processed = len(dry_run_tasks) if dry_run else len(results)
    return TaskRunSummary(
        project_path=str(project_root),
        generated_at=generated_at,
        max_tasks=max_tasks,
        tasks_requested=max_tasks,
        tasks_loaded=tasks_loaded,
        tasks_selected=selected_count,
        tasks_processed=processed,
        tasks_completed=completed,
        tasks_failed=failed_json + failed_model + failed_read,
        failed_json=failed_json,
        failed_model=failed_model,
        failed_read=failed_read,
        json_repaired=sum(1 for result in results if result.json_repaired),
        output_path=str(output_path),
        dry_run=dry_run,
        results=results,
        dry_run_tasks=dry_run_tasks,
        tasks_new=sum(1 for result in results if result.status != "reused"),
        tasks_reused=reused,
        model_used=model_used,
        benchmark_source=benchmark_source,
        prompt_version_used="",
        max_chars_used=0,
        adaptive_limits_enabled=adaptive_enabled,
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _resolve_project_root(project_path: Path | str) -> Path:
    root = Path(project_path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"project path is not a directory: {root}")
    return root


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _config_for_model(config: OllamaConfig, model_name: str) -> OllamaConfig:
    return OllamaConfig(
        base_url=config.base_url,
        model=model_name,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        max_chars_per_file=config.max_chars_per_file,
    )
