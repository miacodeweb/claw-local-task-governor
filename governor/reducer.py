"""Deterministic reduce step for task analysis results."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEVERITIES = ["critical", "high", "medium", "low", "none"]
TASK_STATUSES = ["completed", "reused", "failed_json", "failed_model", "failed_read"]


@dataclass(frozen=True)
class AuditInputs:
    project_path: str
    task_results: dict[str, Any]
    scan_result: dict[str, Any] = field(default_factory=dict)
    tasks_data: dict[str, Any] = field(default_factory=dict)
    results_path: str = ""


def load_audit_inputs(
    project_path: Path | str,
    output_dir: Path | str = "reports",
    results_path: Path | str | None = None,
) -> AuditInputs:
    """Load scanner, queue, and task result files for deterministic reduction."""
    output_path = Path(output_dir)
    task_results_path = Path(results_path) if results_path is not None else output_path / "task_results.json"
    if not task_results_path.exists():
        raise FileNotFoundError(f"task results file not found: {task_results_path}")

    return AuditInputs(
        project_path=str(Path(project_path).expanduser().resolve()),
        scan_result=_load_optional_json(output_path / "scan_result.json"),
        tasks_data=_load_optional_json(output_path / "tasks.json"),
        task_results=_load_json(task_results_path),
        results_path=str(task_results_path),
    )


def build_final_report(inputs: AuditInputs) -> dict[str, Any]:
    """Build a deterministic final report from task result JSON."""
    results = list(inputs.task_results.get("results", []))
    findings = flatten_findings(results)
    findings_by_risk = group_findings_by_risk(findings)
    counts = build_counts(inputs, results, findings)
    model_used = detect_model(results)
    profile_detected = detect_profile(inputs, results)
    graphify = summarize_graphify(inputs)

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_path": inputs.project_path,
            "results_path": inputs.results_path,
            "profile_detected": profile_detected,
            "model_used": model_used,
            "deterministic": True,
            "benchmark_source": inputs.task_results.get("benchmark_source", ""),
            "prompt_version_used": inputs.task_results.get("prompt_version_used", ""),
            "max_chars_used": inputs.task_results.get("max_chars_used", 0),
            "adaptive_limits_enabled": inputs.task_results.get("adaptive_limits_enabled", False),
        },
        "summary": build_summary(counts),
        "counts": counts,
        "graphify": graphify,
        "findings": {
            "all": findings,
            "by_risk": findings_by_risk,
            "by_file": group_items_by_key(findings, "file"),
            "by_type": group_items_by_key(findings, "type"),
        },
        "failed_tasks": summarize_failed_tasks(results),
        "reused_results": summarize_reused_results(results),
        "truncated_files": summarize_truncated_files(results),
        "task_statuses": group_results_by_status(results),
        "json_quality": group_results_by_json_quality(results),
        "recommendations": build_recommendations(counts, findings_by_risk),
        "limitations": build_limitations(counts),
        "report_paths": {
            "markdown": "",
            "json": "",
        },
        # Backwards-compatible fields used by older report/OpenClaw helpers.
        "status": "completed_with_errors" if counts["json_failed"] else "completed",
        "project_path": inputs.project_path,
        "profile_detected": profile_detected,
        "model_used": model_used,
        "totals": counts,
        "graphify_context": graphify,
        "findings_by_priority": findings_by_risk,
        "findings_by_file": group_items_by_key(findings, "file"),
        "findings_by_type": group_items_by_key(findings, "type"),
        "files": summarize_files(results),
    }


def build_counts(
    inputs: AuditInputs,
    results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "files_scanned": int(inputs.scan_result.get("files_found", 0)),
        "relevant_files": int(inputs.scan_result.get("relevant_files", 0)),
        "tasks_total": int(inputs.tasks_data.get("tasks_total", len(inputs.tasks_data.get("tasks", [])))),
        "tasks_requested": int(inputs.task_results.get("tasks_requested", inputs.task_results.get("max_tasks", 0))),
        "tasks_processed": int(inputs.task_results.get("tasks_processed", len(results))),
        "tasks_selected": int(inputs.task_results.get("tasks_selected", len(results))),
        "files_analyzed": sum(1 for result in results if result.get("status") in {"completed", "reused"}),
        "results_reused": sum(1 for result in results if result.get("status") == "reused"),
        "files_reused_from_memory": sum(1 for result in results if result.get("status") == "reused"),
        "graph_enhanced_tasks": count_graph_enhanced_tasks(inputs.tasks_data),
        "json_valid": sum(1 for result in results if result.get("json_valid") is True),
        "json_repaired": sum(1 for result in results if result.get("json_repaired") is True),
        "json_failed": sum(1 for result in results if result.get("json_valid") is not True),
        "failed_tasks": sum(1 for result in results if result.get("status") not in {"completed", "reused"}),
        "truncated_files": sum(1 for result in results if result.get("truncated") is True),
        "findings_total": sum(1 for finding in findings if finding.get("risk") != "none"),
        "critical": len([finding for finding in findings if finding.get("risk") == "critical"]),
        "high": len([finding for finding in findings if finding.get("risk") == "high"]),
        "medium": len([finding for finding in findings if finding.get("risk") == "medium"]),
        "low": len([finding for finding in findings if finding.get("risk") == "low"]),
        "none": len([finding for finding in findings if finding.get("risk") == "none"]),
    }


def summarize_graphify(inputs: AuditInputs) -> dict[str, Any]:
    graphify = inputs.tasks_data.get("graphify", {}) if isinstance(inputs.tasks_data, dict) else {}
    tasks = inputs.tasks_data.get("tasks", []) if isinstance(inputs.tasks_data, dict) else []
    enhanced_tasks = [
        {
            "task_id": task.get("task_id", ""),
            "file": task.get("file_path", ""),
            "reason": task.get("reason", ""),
        }
        for task in tasks
        if isinstance(task, dict) and "graphify:" in str(task.get("reason", ""))
    ]
    central_nodes = list(graphify.get("central_nodes", [])) if isinstance(graphify, dict) else []
    high_connectivity_files = list(graphify.get("high_connectivity_files", [])) if isinstance(graphify, dict) else []
    important_files = list(graphify.get("important_files", [])) if isinstance(graphify, dict) else []
    candidate_files = list(graphify.get("candidate_files", [])) if isinstance(graphify, dict) else []

    return {
        "detected": bool(graphify.get("detected")) if isinstance(graphify, dict) else False,
        "used": bool(graphify.get("used")) if isinstance(graphify, dict) else False,
        "graph_path": graphify.get("graph_path") if isinstance(graphify, dict) else None,
        "nodes": safe_int(graphify.get("nodes_total") or graphify.get("nodes_count")) if isinstance(graphify, dict) else 0,
        "edges": safe_int(graphify.get("edges_total") or graphify.get("edges_count")) if isinstance(graphify, dict) else 0,
        "graph_enhanced_tasks": len(enhanced_tasks),
        "enhanced_tasks": enhanced_tasks,
        "referenced_files": candidate_files,
        "important_files": important_files,
        "central_nodes": central_nodes,
        "high_connectivity_files": high_connectivity_files,
        "communities": list(graphify.get("communities", [])) if isinstance(graphify, dict) else [],
        "surprising_connections": list(graphify.get("surprising_connections", [])) if isinstance(graphify, dict) else [],
        "warnings": list(graphify.get("warnings", [])) if isinstance(graphify, dict) else [],
    }


def count_graph_enhanced_tasks(tasks_data: dict[str, Any]) -> int:
    tasks = tasks_data.get("tasks", []) if isinstance(tasks_data, dict) else []
    return sum(1 for task in tasks if isinstance(task, dict) and "graphify:" in str(task.get("reason", "")))


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def flatten_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for result in results:
        data = result.get("result")
        file_path = str(result.get("file_path") or (data or {}).get("file") or "")
        task_status = str(result.get("status") or "unknown")
        task_id = str(result.get("task_id") or "")

        if not isinstance(data, dict) or result.get("json_valid") is not True:
            continue

        file_findings = data.get("findings", [])
        if file_findings:
            for finding in file_findings:
                if isinstance(finding, dict):
                    findings.append(normalize_finding(file_path, task_id, task_status, finding))
        else:
            findings.append(
                {
                    "task_id": task_id,
                    "file": file_path,
                    "line": None,
                    "type": "none",
                    "risk": "none",
                    "severity": "none",
                    "evidence": str(data.get("summary") or "No findings reported."),
                    "recommendation": "No action required.",
                    "task_status": task_status,
                }
            )

    return sorted(findings, key=lambda item: (risk_sort_key(item.get("risk")), item["file"], str(item["line"]), item["type"]))


def normalize_finding(
    file_path: str,
    task_id: str,
    task_status: str,
    finding: dict[str, Any],
) -> dict[str, Any]:
    severity = normalize_risk(finding.get("severity") or "low")
    return {
        "task_id": task_id,
        "file": file_path,
        "line": finding.get("line"),
        "type": str(finding.get("type") or "unknown"),
        "risk": severity,
        "severity": severity,
        "evidence": str(finding.get("evidence") or ""),
        "recommendation": str(finding.get("recommendation") or ""),
        "task_status": task_status,
    }


def group_findings_by_risk(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {risk: [] for risk in SEVERITIES}
    for finding in findings:
        grouped[normalize_risk(finding.get("risk"))].append(finding)
    return grouped


def group_items_by_key(items: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item.get(key) or "unknown")].append(item)
    return {name: grouped[name] for name in sorted(grouped)}


def group_results_by_status(results: list[dict[str, Any]]) -> dict[str, int]:
    grouped = {status: 0 for status in TASK_STATUSES}
    for result in results:
        status = str(result.get("status") or "unknown")
        grouped[status] = grouped.get(status, 0) + 1
    return grouped


def group_results_by_json_quality(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "valid": sum(1 for result in results if result.get("json_valid") is True),
        "repaired": sum(1 for result in results if result.get("json_repaired") is True),
        "failed": sum(1 for result in results if result.get("json_valid") is not True),
    }


def summarize_failed_tasks(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed = []
    for result in results:
        if result.get("status") in {"completed", "reused"}:
            continue
        failed.append(
            {
                "task_id": result.get("task_id", ""),
                "file": result.get("file_path", ""),
                "status": result.get("status", ""),
                "json_valid": bool(result.get("json_valid")),
                "errors": list(result.get("errors", [])),
            }
        )
    return failed


def summarize_reused_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "task_id": result.get("task_id", ""),
            "file": result.get("file_path", ""),
            "task_type": result.get("task_type", ""),
            "model": result.get("model", ""),
            "created_at": result.get("created_at", ""),
        }
        for result in results
        if result.get("status") == "reused"
    ]


def summarize_truncated_files(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "task_id": result.get("task_id", ""),
            "file": result.get("file_path", ""),
            "task_type": result.get("task_type", ""),
        }
        for result in results
        if result.get("truncated") is True
    ]


def summarize_files(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    files = []
    for result in results:
        data = result.get("result") if isinstance(result.get("result"), dict) else {}
        files.append(
            {
                "file": result.get("file_path", ""),
                "status": result.get("status", ""),
                "risk": result.get("risk", data.get("risk", "none")),
                "json_valid": bool(result.get("json_valid")),
                "json_repaired": bool(result.get("json_repaired")),
                "truncated": bool(result.get("truncated")),
                "summary": data.get("summary", ""),
            }
        )
    return files


def build_summary(counts: dict[str, int]) -> str:
    return (
        f"Reduced {counts['tasks_processed']} processed tasks with "
        f"{counts['findings_total']} actionable findings, "
        f"{counts['results_reused']} reused results, "
        f"{counts['json_repaired']} repaired JSON responses, and "
        f"{counts['json_failed']} JSON failures."
    )


def build_recommendations(
    counts: dict[str, int],
    findings_by_risk: dict[str, list[dict[str, Any]]],
) -> list[str]:
    recommendations = []
    if findings_by_risk["critical"]:
        recommendations.append("Review critical findings first before running broader audits.")
    if findings_by_risk["high"]:
        recommendations.append("Address high risk findings before lower priority cleanup.")
    if counts["json_failed"]:
        recommendations.append("Rerun failed JSON tasks or inspect raw model output before relying on totals.")
    if counts["truncated_files"]:
        recommendations.append("Review truncated files with a higher max_chars_per_file if important context was omitted.")
    if counts["results_reused"]:
        recommendations.append("Reused memory results were included; rescan and rerun tasks after source changes.")
    if not recommendations:
        recommendations.append("No urgent action was detected in the analyzed files.")
    return recommendations


def build_limitations(counts: dict[str, int]) -> list[str]:
    limitations = [
        "This report is generated deterministically from task_results.json; no model reviewed the final report.",
        "Findings are limited to files and content processed by run-tasks.",
    ]
    if counts["truncated_files"]:
        limitations.append("Some files were truncated before model analysis.")
    if counts["json_failed"]:
        limitations.append("Some tasks failed JSON validation and may need rerun.")
    return limitations


def detect_model(results: list[dict[str, Any]]) -> str:
    models = sorted({str(result.get("model")) for result in results if result.get("model")})
    return ", ".join(models) if models else "unknown"


def detect_profile(inputs: AuditInputs, results: list[dict[str, Any]]) -> str:
    result_profiles = sorted({str(result.get("profile")) for result in results if result.get("profile")})
    return str(
        inputs.scan_result.get("profile_detected")
        or inputs.tasks_data.get("profile")
        or inputs.task_results.get("profile")
        or (result_profiles[0] if result_profiles else "general")
    )


def normalize_risk(value: Any) -> str:
    risk = str(value or "low").lower()
    return risk if risk in SEVERITIES else "low"


def risk_sort_key(value: Any) -> int:
    return SEVERITIES.index(normalize_risk(value))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)
