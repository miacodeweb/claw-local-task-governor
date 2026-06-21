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


ALLOWED_PROFILES = {"auto", "general", "php", "wordpress", "javascript", "python", "java", "docker"}
ALLOWED_MODES = {"general", "security", "code_quality", "performance", "seo"}
DEFAULT_OUTPUT_DIR = Path("reports")
AUDIT_JSON_PATTERN = "audit-*.json"


def local_project_audit(
    *,
    path: Path | str,
    profile: str = "auto",
    mode: str = "general",
    max_files: int = 50,
    read_only: bool = True,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> dict[str, Any]:
    """Run the read-only scan -> tasks -> run-tasks -> report flow."""
    profile = validate_choice("profile", profile, ALLOWED_PROFILES)
    mode = validate_choice("mode", mode, ALLOWED_MODES)
    if max_files < 1:
        raise ValueError("max_files must be greater than 0")
    if read_only is not True:
        return rejected_response("read_only must be true; editing is not supported")

    project_root = Path(path).expanduser().resolve(strict=True)
    if not project_root.is_dir():
        raise NotADirectoryError(f"project path is not a directory: {project_root}")

    output_path = Path(output_dir)
    scan_result = scan_project(project_root, output_dir=output_path)
    scan_result_path = output_path / "scan_result.json"
    if profile != "auto":
        write_profile_override(scan_result_path, profile)

    generate_tasks_from_scan_result(scan_result_path, output_dir=output_path)
    run_pending_tasks(
        project_root,
        max_tasks=max_files,
        output_dir=output_path,
        client=client,
        memory=memory,
    )

    inputs = load_audit_inputs(project_root, output_dir=output_path)
    report = build_final_report(inputs)
    report["mode"] = mode
    report["profile_requested"] = profile
    markdown_path, _ = write_audit_reports(report, output_dir=output_path)
    totals = report.get("totals", {})

    return {
        "status": report.get("status", "completed"),
        "report_path": str(markdown_path.resolve()),
        "summary": report.get("summary", ""),
        "files_scanned": int(totals.get("files_scanned", scan_result.files_found)),
        "files_analyzed": int(totals.get("files_analyzed", 0)),
        "files_reused_from_memory": int(totals.get("files_reused_from_memory", 0)),
        "json_valid": int(totals.get("json_valid", 0)),
        "json_repaired": int(totals.get("json_repaired", 0)),
        "json_failed": int(totals.get("json_failed", 0)),
    }


def validate_choice(name: str, value: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_values}")
    return normalized


def rejected_response(summary: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "report_path": "",
        "summary": summary,
        "files_scanned": 0,
        "files_analyzed": 0,
        "files_reused_from_memory": 0,
        "json_valid": 0,
        "json_repaired": 0,
        "json_failed": 0,
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
