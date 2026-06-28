"""Shared safety validation helpers for LocalScope adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MAX_TASKS_LIMIT = 100
STATUS_LIMIT_DEFAULT = 5
STATUS_LIMIT_MAX = 20
ALLOWED_MCP_TOOLS = {
    "localscope_audit",
    "localscope_status",
    "localscope_report",
    "localscope_graph_info",
}
FORBIDDEN_TOOL_NAMES = {"read_file", "write_file", "run_command", "apply_patch", "shell", "exec"}


def normalize_path_text(value: Any) -> str:
    """Normalize user-supplied path text without broad filesystem access."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    if "\x00" in text:
        raise ValueError("path contains an invalid null byte")
    return text


def validate_project_path(value: Any) -> Path:
    """Resolve a project directory path safely for audit/query entrypoints."""
    text = normalize_path_text(value)
    if not text:
        raise ValueError("path is required")

    try:
        resolved = Path(text).expanduser().resolve(strict=True)
    except OSError as error:
        raise ValueError(f"project path does not exist: {text}") from error

    if not resolved.is_dir():
        raise ValueError(f"project path is not a directory: {resolved}")
    if _is_filesystem_root(resolved):
        raise ValueError(f"project path must not be a filesystem root: {resolved}")
    return resolved


def validate_max_tasks(value: Any, *, maximum: int = MAX_TASKS_LIMIT) -> int:
    """Validate a positive bounded task limit."""
    try:
        max_tasks = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("max_tasks must be an integer") from error

    if max_tasks < 1:
        raise ValueError("max_tasks must be greater than 0")
    if max_tasks > maximum:
        raise ValueError(f"max_tasks must be less than or equal to {maximum}")
    return max_tasks


def validate_read_only(value: Any) -> None:
    """Reject any adapter request that is not explicitly read-only."""
    if value is not True:
        raise ValueError("read_only=false rejected")


def validate_report_path(value: Any, *, reports_root: Path | str) -> Path:
    """Allow only LocalScope-owned reports/audit-* markdown or JSON files."""
    text = normalize_path_text(value)
    if not text:
        raise ValueError("report_path is required")

    try:
        resolved = Path(text).expanduser().resolve(strict=True)
    except OSError as error:
        raise ValueError(str(error)) from error

    if resolved.suffix.lower() not in {".json", ".md"}:
        raise ValueError("report_path must point to a .json or .md report")
    if not resolved.name.startswith("audit-"):
        raise ValueError("report_path must point to a LocalScope audit-* report")

    root = Path(reports_root).expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"report_path must be inside {root}") from error
    return resolved


def validate_mcp_tool_names(tool_names: set[str]) -> None:
    """Ensure MCP exposes only the intended high-level tools."""
    forbidden = sorted(tool_names & FORBIDDEN_TOOL_NAMES)
    if forbidden:
        raise ValueError(f"forbidden MCP tools exposed: {', '.join(forbidden)}")
    unexpected = sorted(tool_names - ALLOWED_MCP_TOOLS)
    if unexpected:
        raise ValueError(f"unexpected MCP tools exposed: {', '.join(unexpected)}")


def _is_filesystem_root(path: Path) -> bool:
    return path.parent == path or str(path) == path.anchor
