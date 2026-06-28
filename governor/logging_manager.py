"""Structured JSONL logging for LocalScope production and debug.

All logs go to `logs/` subdirectories as append-only JSONL.
Stdout is never touched — adapters (MCP/OpenClaw/OpenCode) need clean JSON.
Human/debug output goes to stderr when needed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_DIR = Path("logs")
LOG_TASKS_DIR = LOG_DIR / "tasks"
LOG_ERRORS_DIR = LOG_DIR / "errors"
LOG_RUNS_DIR = LOG_DIR / "runs"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "level": "info",
    "directory": "logs",
    "jsonl": True,
    "debug_raw_model_output": False,
    "redact_secrets": True,
}

SECRET_PATTERNS = [
    (re.compile(r"(api[_-]?key|apikey)\s*[:=]\s*['\"]?\S+['\"]?", re.IGNORECASE), "api_key=REDACTED"),
    (re.compile(r"(token|access_token)\s*[:=]\s*['\"]?\S+['\"]?", re.IGNORECASE), "token=REDACTED"),
    (re.compile(r"(password|passwd|pwd)\s*[:=]\s*['\"]?\S+['\"]?", re.IGNORECASE), "password=REDACTED"),
    (re.compile(r"(secret|private_key)\s*[:=]\s*['\"]?\S+['\"]?", re.IGNORECASE), "secret=REDACTED"),
    (re.compile(r"(bearer|auth)\s+['\"]?\S+['\"]?", re.IGNORECASE), "bearer=REDACTED"),
]


class LogManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self._enabled = bool(self.config.get("enabled", True))
        self._debug_raw = bool(self.config.get("debug_raw_model_output", False))
        self._redact = bool(self.config.get("redact_secrets", True))
        self._base_dir = Path(str(self.config.get("directory", "logs")))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _write_event(self, category: str, data: dict[str, Any]) -> None:
        if not self._enabled:
            return
        data["timestamp"] = _utc_now()
        dir_path = self._base_dir / category
        dir_path.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d')}.jsonl"
        path = dir_path / filename
        if self._redact:
            data = _redact_dict(data)
        line = json.dumps(data, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- Run events ----

    def run_started(self, command: str, project_path: str = "", profile: str = "", mode: str = "", model_used: str = "", benchmark_source: str = "") -> None:
        self._write_event("runs", {
            "event": "run_started",
            "command": command,
            "project_path": project_path,
            "profile": profile,
            "mode": mode,
            "model_used": model_used,
            "benchmark_source": benchmark_source,
        })

    def run_completed(self, command: str, duration_ms: int = 0, report_markdown: str = "", report_json: str = "", project_path: str = "") -> None:
        self._write_event("runs", {
            "event": "run_completed",
            "command": command,
            "duration_ms": duration_ms,
            "report_markdown": report_markdown,
            "report_json": report_json,
            "project_path": project_path,
        })

    def run_failed(self, command: str, error_message: str, project_path: str = "") -> None:
        self._write_event("runs", {
            "event": "run_failed",
            "command": command,
            "error_message": _truncate(error_message, 500),
            "project_path": project_path,
        })

    # ---- Task events ----

    def task_started(self, task_id: str, task_type: str, file_path: str, model: str = "", prompt_version: str = "", max_chars_used: int = 0, adaptive_enabled: bool = False) -> None:
        self._write_event("tasks", {
            "event": "task_started",
            "task_id": task_id,
            "task_type": task_type,
            "file_path": file_path,
            "model": model,
            "prompt_version": prompt_version,
            "max_chars_used": max_chars_used,
            "adaptive_limits_enabled": adaptive_enabled,
        })

    def task_completed(self, task_id: str, task_type: str, file_path: str, model: str = "", duration_ms: int = 0, json_valid: bool = False, json_repaired: bool = False, reused: bool = False, severity_counts: dict[str, int] | None = None) -> None:
        self._write_event("tasks", {
            "event": "task_completed",
            "task_id": task_id,
            "task_type": task_type,
            "file_path": file_path,
            "model": model,
            "duration_ms": duration_ms,
            "json_valid": json_valid,
            "json_repaired": json_repaired,
            "reused_from_memory": reused,
            "severity_counts": severity_counts or {},
        })

    def task_failed(self, task_id: str, task_type: str, file_path: str, model: str = "", error_message: str = "", reason: str = "") -> None:
        self._write_event("tasks", {
            "event": "task_failed",
            "task_id": task_id,
            "task_type": task_type,
            "file_path": file_path,
            "model": model,
            "error_message": _truncate(error_message, 500),
            "reason": reason,
        })

    # ---- Error events ----

    def log_error(self, error_type: str, error_message: str, command: str = "", task_id: str = "", file_path: str = "", model: str = "", traceback_str: str = "") -> None:
        event: dict[str, Any] = {
            "event": "error",
            "error_type": error_type,
            "error_message": _truncate(error_message, 500),
            "command": command,
            "task_id": task_id,
            "file_path": file_path,
            "model": model,
        }
        if self._debug_raw and traceback_str:
            event["traceback"] = _truncate(traceback_str, 2000)
        self._write_event("errors", event)

    # ---- Benchmark events ----

    def benchmark_started(self, models: list[str], max_tasks: int = 0, project_path: str = "") -> None:
        self._write_event("runs", {
            "event": "benchmark_started",
            "models": models,
            "max_tasks": max_tasks,
            "project_path": project_path,
        })

    def benchmark_completed(self, models: list[str], json_path: str = "", duration_ms: int = 0) -> None:
        self._write_event("runs", {
            "event": "benchmark_completed",
            "models": models,
            "json_path": json_path,
            "duration_ms": duration_ms,
        })

    def benchmark_failed(self, models: list[str], error_message: str = "") -> None:
        self._write_event("runs", {
            "event": "benchmark_failed",
            "models": models,
            "error_message": _truncate(error_message, 500),
        })


# Singleton
_log_manager: LogManager | None = None


def get_log_manager(config: dict[str, Any] | None = None, reload: bool = False) -> LogManager:
    global _log_manager
    if _log_manager is None or reload:
        _log_manager = LogManager(config)
    return _log_manager


# ---- Log reader helpers ----

def read_log_summary(
    log_dir: Path | str = LOG_DIR,
    *, lines_per_category: int = 500
) -> dict[str, Any]:
    base = Path(log_dir)
    summary: dict[str, Any] = {"runs": 0, "tasks": 0, "errors": 0, "latest": {}}
    for category, path in [("runs", base / "runs"), ("tasks", base / "tasks"), ("errors", base / "errors")]:
        count = 0
        latest_entry: dict[str, Any] | None = None
        if path.is_dir():
            for f in sorted(path.glob("*.jsonl"), reverse=True):
                try:
                    lines = f.read_text(encoding="utf-8").strip().splitlines()
                    take = min(len(lines), lines_per_category - count)
                    for line in lines[-take:]:
                        count += 1
                        if latest_entry is None:
                            try:
                                latest_entry = json.loads(line)
                            except json.JSONDecodeError:
                                pass
                except OSError:
                    pass
        summary[category] = count
        if latest_entry:
            summary["latest"][category] = latest_entry
    return summary


def read_log_errors(
    log_dir: Path | str = LOG_DIR, *, limit: int = 20
) -> list[dict[str, Any]]:
    return _read_last_lines(Path(log_dir) / "errors", limit=limit)


def read_log_tasks(
    log_dir: Path | str = LOG_DIR, *, limit: int = 20
) -> list[dict[str, Any]]:
    return _read_last_lines(Path(log_dir) / "tasks", limit=limit)


def _read_last_lines(category_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not category_dir.is_dir():
        return results
    for f in sorted(category_dir.glob("*.jsonl"), reverse=True):
        try:
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if len(results) >= limit:
                    break
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            if len(results) >= limit:
                break
        except OSError:
            pass
    return results


def _redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = _redact_text(value)
        elif isinstance(value, dict):
            result[key] = _redact_dict(value)
        else:
            result[key] = value
    return result


def _redact_text(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
