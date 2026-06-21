"""Controlled execution of pending microtasks with Ollama and JSON Guard."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governor.json_guard import JSONGuardResult, guard_json
from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory
from governor.ollama_client import OllamaClient, OllamaError, load_ollama_config
from governor.prompt_renderer import PromptRenderError, render_prompt


DEFAULT_OUTPUT_DIR = Path("reports")
TASKS_FILENAME = "tasks.json"
TASK_RESULTS_FILENAME = "task_results.json"
FILE_ANALYSIS_SCHEMA = "file_analysis.schema.json"
PROMPT_VERSION = "file-analysis-v1"


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    project_path: str
    file_path: str
    file_hash: str
    task_type: str
    profile: str
    status: str
    json_valid: bool
    json_repaired: bool
    risk: str
    result: Any
    errors: list[str]
    raw_response: str
    created_at: str


@dataclass(frozen=True)
class TaskRunSummary:
    project_path: str
    generated_at: str
    max_tasks: int
    tasks_loaded: int
    tasks_selected: int
    tasks_completed: int
    tasks_failed: int
    tasks_new: int
    tasks_reused: int
    results: list[TaskRunResult]

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "generated_at": self.generated_at,
            "max_tasks": self.max_tasks,
            "tasks_loaded": self.tasks_loaded,
            "tasks_selected": self.tasks_selected,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_new": self.tasks_new,
            "tasks_reused": self.tasks_reused,
            "results": [asdict(result) for result in self.results],
        }


def run_pending_tasks(
    project_path: Path | str,
    *,
    max_tasks: int,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> TaskRunSummary:
    """Run a limited number of pending tasks from reports/tasks.json."""
    if max_tasks < 1:
        raise ValueError("max_tasks must be greater than 0")

    project_root = _resolve_project_root(project_path)
    output_path = Path(output_dir)
    tasks_path = output_path / TASKS_FILENAME
    tasks_data = _load_json_file(tasks_path)
    pending_tasks = [task for task in tasks_data.get("tasks", []) if task.get("status") == "pending"]
    selected_tasks = pending_tasks[:max_tasks]
    runner_client = client or OllamaClient(load_ollama_config())
    config = runner_client.config
    task_memory = memory or SQLiteMemory(DEFAULT_MEMORY_PATH)
    results: list[TaskRunResult] = []

    for task in selected_tasks:
        results.append(
            run_single_task(
                task,
                project_root=project_root,
                client=runner_client,
                fallback_max_chars=config.max_chars_per_file,
                memory=task_memory,
                model=config.model,
                prompt_version=PROMPT_VERSION,
            )
        )

    summary = TaskRunSummary(
        project_path=str(project_root),
        generated_at=datetime.now(timezone.utc).isoformat(),
        max_tasks=max_tasks,
        tasks_loaded=len(tasks_data.get("tasks", [])),
        tasks_selected=len(selected_tasks),
        tasks_completed=sum(1 for result in results if result.status == "completed"),
        tasks_failed=sum(1 for result in results if result.status not in {"completed", "reused"}),
        tasks_new=sum(1 for result in results if result.status != "reused"),
        tasks_reused=sum(1 for result in results if result.status == "reused"),
        results=results,
    )
    write_task_results(summary, output_path)
    return summary


def run_single_task(
    task: dict,
    *,
    project_root: Path,
    client: OllamaClient,
    fallback_max_chars: int,
    memory: SQLiteMemory,
    model: str,
    prompt_version: str,
) -> TaskRunResult:
    created_at = datetime.now(timezone.utc).isoformat()
    raw_response = ""
    response_time_seconds: float | None = None

    try:
        file_path = resolve_task_file(project_root, task["file_path"])
        reusable = memory.find_reusable_result(
            project_path=str(project_root),
            file_path=task["file_path"],
            file_hash=task["file_hash"],
            task_type=task["task_type"],
            model=model,
            prompt_version=prompt_version,
        )
        if reusable is not None:
            return _result_from_reusable(task, reusable, created_at)

        max_chars = memory.recommended_max_chars(
            model,
            task["task_type"],
            fallback=fallback_max_chars,
        )
        file_content = read_text_limited(file_path, max_chars)
        prompt = render_task_prompt(task, file_content)
        started_at = time.perf_counter()
        raw_response = client.analyze_text_with_model(prompt, file_content)
        response_time_seconds = time.perf_counter() - started_at
        guarded = guard_json(raw_response, FILE_ANALYSIS_SCHEMA)
        result = _result_from_guard(task, guarded, raw_response, created_at)
        memory.save_task_result(
            project_path=str(project_root),
            project_type=task.get("profile", "general"),
            file_path=task["file_path"],
            file_hash=task["file_hash"],
            task_type=task["task_type"],
            model=model,
            prompt_version=prompt_version,
            json_valid=result.json_valid,
            json_repaired=result.json_repaired,
            risk=result.risk,
            result_json=result.result if isinstance(result.result, dict) else None,
            response_time_seconds=response_time_seconds,
            current_max_chars=max_chars,
        )
        return result
    except PromptRenderError as error:
        return _failed_result(task, "failed_prompt", [str(error)], raw_response, created_at)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return _failed_result(task, "failed_file", [str(error)], raw_response, created_at)
    except OllamaError as error:
        return _failed_result(task, "failed_model", [str(error)], raw_response, created_at)


def render_task_prompt(task: dict, file_content: str) -> str:
    task_type = task.get("task_type", "inspect_unknown_file")
    supported_type = task_type if task_type in {"inspect_code_file", "inspect_config_file"} else "inspect_code_file"
    return render_prompt(
        file_path=task["file_path"],
        profile=task.get("profile", "general"),
        task_type=supported_type,
        file_content=file_content,
    )


def resolve_task_file(project_root: Path, task_file_path: str) -> Path:
    file_path = (project_root / task_file_path).resolve(strict=True)
    if not _is_relative_to(file_path, project_root):
        raise ValueError(f"task file path escapes project root: {task_file_path}")
    if not file_path.is_file():
        raise ValueError(f"task path is not a file: {task_file_path}")
    return file_path


def read_text_limited(path: Path, max_chars: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(max_chars)


def write_task_results(summary: TaskRunSummary, output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Path:
    output_path = Path(output_dir) / TASK_RESULTS_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    return output_path


def _result_from_guard(
    task: dict,
    guarded: JSONGuardResult,
    raw_response: str,
    created_at: str,
) -> TaskRunResult:
    status = "completed" if guarded.valid else "failed_json"
    data = guarded.data if guarded.valid else None
    risk = data.get("risk", "none") if isinstance(data, dict) else "none"
    return TaskRunResult(
        task_id=task["task_id"],
        project_path=task["project_path"],
        file_path=task["file_path"],
        file_hash=task["file_hash"],
        task_type=task["task_type"],
        profile=task.get("profile", "general"),
        status=status,
        json_valid=guarded.valid,
        json_repaired=guarded.repaired,
        risk=risk,
        result=data,
        errors=guarded.errors,
        raw_response=raw_response,
        created_at=created_at,
    )


def _result_from_reusable(
    task: dict,
    reusable: Any,
    created_at: str,
) -> TaskRunResult:
    return TaskRunResult(
        task_id=task["task_id"],
        project_path=task["project_path"],
        file_path=task["file_path"],
        file_hash=task["file_hash"],
        task_type=task["task_type"],
        profile=task.get("profile", "general"),
        status="reused",
        json_valid=reusable.json_valid,
        json_repaired=reusable.json_repaired,
        risk=reusable.risk,
        result=reusable.result_json,
        errors=[],
        raw_response="",
        created_at=created_at,
    )


def _failed_result(
    task: dict,
    status: str,
    errors: list[str],
    raw_response: str,
    created_at: str,
) -> TaskRunResult:
    return TaskRunResult(
        task_id=task.get("task_id", ""),
        project_path=task.get("project_path", ""),
        file_path=task.get("file_path", ""),
        file_hash=task.get("file_hash", ""),
        task_type=task.get("task_type", "inspect_unknown_file"),
        profile=task.get("profile", "general"),
        status=status,
        json_valid=False,
        json_repaired=False,
        risk="none",
        result=None,
        errors=errors,
        raw_response=raw_response,
        created_at=created_at,
    )


def _load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
