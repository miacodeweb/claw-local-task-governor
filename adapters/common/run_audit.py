"""Shared LocalScope audit runner for external adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.common.audit_request import AuditRequest
from adapters.common.audit_response import AuditResponse
from governor.memory import SQLiteMemory
from governor.ollama_client import OllamaClient
from governor.reducer import build_final_report, load_audit_inputs
from governor.report_writer import write_audit_reports
from governor.safety import validate_project_path
from governor.scanner import scan_project
from governor.task_queue import generate_tasks_from_scan_result
from governor.task_runner import run_pending_tasks


DEFAULT_OUTPUT_DIR = Path("reports")


def run_audit(
    request: AuditRequest | dict[str, Any],
    *,
    adapter: str = "cli",
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
    dry_run: bool = False,
) -> AuditResponse:
    """Run scan -> tasks -> run-tasks -> report and always return a response object."""
    try:
        audit_request = request if isinstance(request, AuditRequest) else AuditRequest.from_dict(request)
    except (TypeError, ValueError) as error:
        return AuditResponse.failed(adapter=adapter, summary=str(error), errors=[str(error)])

    if audit_request.read_only is not True:
        return AuditResponse.failed(
            adapter=adapter,
            project_path=audit_request.path,
            summary="read_only must be true; editing is not supported",
            errors=["read_only=false rejected"],
        )

    try:
        project_root = validate_project_path(audit_request.path)

        output_path = Path(output_dir)
        scan_result = scan_project(project_root, output_dir=output_path, profile=audit_request.core_profile)
        scan_result_path = output_path / "scan_result.json"
        generate_tasks_from_scan_result(
            scan_result_path,
            output_dir=output_path,
            use_graphify=audit_request.use_graphify,
        )
        task_summary = run_pending_tasks(
            project_root,
            max_tasks=audit_request.max_tasks,
            output_dir=output_path,
            client=client,
            memory=memory if audit_request.use_memory else None,
            no_memory=not audit_request.use_memory,
            profile_override=audit_request.core_profile,
            dry_run=dry_run,
            no_adaptive_limits=not audit_request.use_adaptive_limits,
            prompt_version=audit_request.prompt_version,
            model_override=audit_request.model_override,
            use_benchmark_recommendations=audit_request.use_benchmark_recommendations,
        )
        if dry_run:
            return AuditResponse(
                status="completed",
                adapter=adapter,
                project_path=str(project_root),
                profile_detected=scan_result.profile_detected,
                tasks_processed=task_summary.tasks_processed,
                summary=(
                    "Audit dry-run completed. "
                    f"Tasks selected: {task_summary.tasks_selected}. "
                    "No model calls or final reports were generated."
                ),
                errors=[],
            )

        inputs = load_audit_inputs(project_root, output_dir=output_path)
        report = build_final_report(inputs)
        report["mode"] = audit_request.mode
        report["profile_requested"] = audit_request.profile
        report["adapter"] = adapter
        markdown_path, json_path = write_audit_reports(report, output_dir=output_path)
        totals = report.get("totals", {})

        return AuditResponse(
            status="completed",
            adapter=adapter,
            project_path=str(project_root),
            profile_detected=str(report.get("profile_detected") or scan_result.profile_detected),
            report_markdown=str(markdown_path.resolve()),
            report_json=str(json_path.resolve()),
            tasks_processed=int(totals.get("tasks_processed", task_summary.tasks_processed)),
            reused=int(totals.get("results_reused", task_summary.tasks_reused)),
            json_valid=int(totals.get("json_valid", 0)),
            json_repaired=int(totals.get("json_repaired", 0)),
            json_failed=int(totals.get("json_failed", 0)),
            summary=str(report.get("summary", "")),
            errors=[],
            model_used=task_summary.model_used or "",
            benchmark_source=task_summary.benchmark_source or "",
            prompt_version_used=task_summary.prompt_version_used or "",
            max_chars_used=task_summary.max_chars_used or 0,
            adaptive_limits_enabled=task_summary.adaptive_limits_enabled,
        )
    except Exception as error:  # noqa: BLE001 - adapter boundary must return JSON-safe failures.
        return AuditResponse.failed(
            adapter=adapter,
            project_path=audit_request.path,
            summary=str(error),
            errors=[str(error)],
        )
