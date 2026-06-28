"""Single high-level OpenClaw-facing tool wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governor.memory import SQLiteMemory
from governor.ollama_client import OllamaClient
from governor.reducer import build_final_report, load_audit_inputs
from governor.report_writer import write_audit_reports
from governor.scanner import scan_project
from governor.task_queue import generate_tasks_from_scan_result
from governor.task_runner import run_pending_tasks


ALLOWED_PROFILES = {
    "auto",
    "general",
    "php",
    "wordpress",
    "javascript",
    "python",
    "java",
    "docker",
    "config_files",
    "windows_folder",
    "linux_folder",
    "documentation",
}
ALLOWED_MODES = {"general", "security", "code_quality"}
DEFAULT_OUTPUT_DIR = Path("reports")
AUDIT_JSON_PATTERN = "audit-*.json"


def local_project_audit(
    *,
    path: Path | str,
    profile: str = "auto",
    mode: str = "general",
    max_tasks: int | None = None,
    max_files: int | None = None,
    use_memory: bool = True,
    use_graphify: bool = True,
    read_only: bool = True,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> dict[str, Any]:
    """Run the read-only audit through the shared LocalScope adapter contract."""
    from adapters.openclaw.local_project_audit import local_project_audit as adapter_audit

    response = adapter_audit(
        path=path,
        profile=profile,
        mode=mode,
        max_tasks=max_tasks,
        max_files=max_files,
        use_memory=use_memory,
        use_graphify=use_graphify,
        read_only=read_only,
        output_dir=output_dir,
        client=client,
        memory=memory,
    )
    return with_legacy_fields(response)


def with_legacy_fields(response: dict[str, Any]) -> dict[str, Any]:
    """Keep earlier OpenClaw CLI/test fields while the new adapter contract settles."""
    totals = {}
    report_json = response.get("report_json")
    if report_json:
        try:
            report = json.loads(Path(report_json).read_text(encoding="utf-8"))
            totals = report.get("totals", {})
        except (OSError, json.JSONDecodeError):
            totals = {}

    response.setdefault("report_path", response.get("report_markdown", ""))
    response.setdefault("files_scanned", int(totals.get("files_scanned", 0)))
    response.setdefault("files_analyzed", int(totals.get("files_analyzed", response.get("tasks_processed", 0))))
    response.setdefault(
        "files_reused_from_memory",
        int(totals.get("files_reused_from_memory", response.get("reused", 0))),
    )
    return response


def validate_choice(name: str, value: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_values}")
    return normalized


def failed_response(summary: str, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "failed",
        "adapter": "openclaw",
        "project_path": "",
        "profile_detected": "",
        "report_markdown": "",
        "report_json": "",
        "tasks_processed": 0,
        "reused": 0,
        "json_valid": 0,
        "json_repaired": 0,
        "json_failed": 0,
        "summary": summary,
        "errors": errors or [],
        "report_path": "",
        "files_scanned": 0,
        "files_analyzed": 0,
        "files_reused_from_memory": 0,
    }


def write_profile_override(scan_result_path: Path, profile: str) -> None:
    scan_result = json.loads(scan_result_path.read_text(encoding="utf-8"))
    scan_result["profile_detected"] = profile
    scan_result_path.write_text(json.dumps(scan_result, indent=2), encoding="utf-8")


def local_audit_status(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    limit: int = 5,
) -> dict[str, Any]:
    """Return recent audit report status without running analysis."""
    if limit < 1:
        raise ValueError("limit must be greater than 0")

    output_path = Path(output_dir)
    audits = list_recent_audits(output_path, limit=limit)
    task_results = load_optional_json(output_path / "task_results.json")
    current = summarize_task_results(task_results) if task_results else {}

    return {
        "status": "completed" if audits else "no_audits",
        "output_dir": str(output_path.resolve()),
        "audits_count": len(audits),
        "recent_audits": audits,
        "current_task_results": current,
    }


def local_audit_report(*, report_path: Path | str) -> dict[str, Any]:
    """Return a compact summary for an existing final audit report."""
    json_path = resolve_report_json_path(Path(report_path))
    report = json.loads(json_path.read_text(encoding="utf-8"))
    totals = report.get("totals", {})

    return {
        "status": report.get("status", "unknown"),
        "report_path": str(json_path.with_suffix(".md").resolve()),
        "json_report_path": str(json_path.resolve()),
        "summary": report.get("summary", ""),
        "profile_detected": report.get("profile_detected", "general"),
        "files_scanned": int(totals.get("files_scanned", 0)),
        "files_analyzed": int(totals.get("files_analyzed", 0)),
        "files_reused_from_memory": int(totals.get("files_reused_from_memory", 0)),
        "json_valid": int(totals.get("json_valid", 0)),
        "json_repaired": int(totals.get("json_repaired", 0)),
        "json_failed": int(totals.get("json_failed", 0)),
        "findings_by_priority": count_findings_by_priority(report),
        "failed_tasks": len(report.get("failed_tasks", [])),
        "recommendations": list(report.get("recommendations", [])),
    }


def list_recent_audits(output_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []

    report_paths = sorted(
        output_dir.glob(AUDIT_JSON_PATTERN),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    audits = []
    for json_path in report_paths[:limit]:
        report = load_optional_json(json_path)
        totals = report.get("totals", {}) if report else {}
        audits.append(
            {
                "status": report.get("status", "unknown") if report else "unreadable",
                "report_path": str(json_path.with_suffix(".md").resolve()),
                "json_report_path": str(json_path.resolve()),
                "summary": report.get("summary", "") if report else "",
                "files_analyzed": int(totals.get("files_analyzed", 0)),
                "json_failed": int(totals.get("json_failed", 0)),
                "updated_at": json_path.stat().st_mtime,
            }
        )
    return audits


def summarize_task_results(task_results: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_path": task_results.get("project_path", ""),
        "generated_at": task_results.get("generated_at", ""),
        "tasks_selected": int(task_results.get("tasks_selected", 0)),
        "tasks_completed": int(task_results.get("tasks_completed", 0)),
        "tasks_failed": int(task_results.get("tasks_failed", 0)),
        "tasks_reused": int(task_results.get("tasks_reused", 0)),
    }


def count_findings_by_priority(report: dict[str, Any]) -> dict[str, int]:
    grouped = report.get("findings_by_priority", {})
    return {priority: len(findings) for priority, findings in grouped.items()}


def resolve_report_json_path(report_path: Path) -> Path:
    path = report_path.expanduser().resolve(strict=True)
    if path.suffix.lower() == ".json":
        return path

    json_path = path.with_suffix(".json")
    if json_path.exists():
        return json_path
    raise FileNotFoundError(f"matching JSON report was not found for: {path}")


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
