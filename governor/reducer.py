"""Deterministic reduce step for task analysis results."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from governor.graphify_adapter import load_graphify_context
from governor.memory import DEFAULT_MEMORY_PATH, SQLiteMemory


SEVERITIES = ["critical", "high", "medium", "low", "none"]


@dataclass(frozen=True)
class AuditInputs:
    project_path: str
    scan_result: dict[str, Any]
    tasks_data: dict[str, Any]
    task_results: dict[str, Any]
    graphify: dict[str, Any] = field(default_factory=dict)
    model_profiles: list[dict[str, Any]] = field(default_factory=list)


def load_audit_inputs(
    project_path: Path | str,
    output_dir: Path | str = "reports",
) -> AuditInputs:
    """Load scanner, queue, and task result files for report reduction."""
    output_path = Path(output_dir)
    return AuditInputs(
        project_path=str(Path(project_path).expanduser().resolve()),
        scan_result=_load_optional_json(output_path / "scan_result.json"),
        tasks_data=_load_optional_json(output_path / "tasks.json"),
        task_results=_load_optional_json(output_path / "task_results.json"),
        graphify=load_graphify_context(project_path),
        model_profiles=load_model_profiles(),
    )


def build_final_report(inputs: AuditInputs) -> dict[str, Any]:
    """Build a deterministic final report from task result JSON."""
    results = list(inputs.task_results.get("results", []))
    findings = flatten_findings(results)
    grouped_by_severity = group_findings_by_severity(findings)

    totals = {
        "files_scanned": int(inputs.scan_result.get("files_found", 0)),
        "relevant_files": int(inputs.scan_result.get("relevant_files", 0)),
        "tasks_total": int(inputs.tasks_data.get("tasks_total", len(inputs.tasks_data.get("tasks", [])))),
        "tasks_selected": int(inputs.task_results.get("tasks_selected", len(results))),
        "files_analyzed": count_analyzed_files(results),
        "files_reused_from_memory": count_reused_results(results),
        "json_valid": count_json_valid(results),
        "json_repaired": count_json_repaired(results),
        "json_failed": count_json_failed(results),
        "findings_total": count_actionable_findings(findings),
    }

    return {
        "status": "completed_with_errors" if totals["json_failed"] else "completed",
        "project_path": inputs.project_path,
        "profile_detected": detect_profile(inputs),
        "graphify": graphify_summary(inputs),
        "model_profiles": inputs.model_profiles,
        "summary": build_summary(totals, grouped_by_severity),
        "totals": totals,
        "findings_by_priority": grouped_by_severity,
        "findings_by_file": group_findings_by_key(findings, "file"),
        "findings_by_type": group_findings_by_key(findings, "type"),
        "files": summarize_files(results),
        "failed_tasks": summarize_failed_tasks(results),
        "recommendations": build_recommendations(totals, grouped_by_severity),
    }


def flatten_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for result in results:
        data = result.get("result")
        file_path = result.get("file_path") or (data or {}).get("file") or ""
        status = result.get("status", "")

        if not isinstance(data, dict) or result.get("json_valid") is not True:
            continue

        file_findings = data.get("findings", [])
        if file_findings:
            for finding in file_findings:
                if not isinstance(finding, dict):
                    continue
                findings.append(normalize_finding(file_path, finding, status))
        else:
            findings.append(
                {
                    "file": file_path,
                    "line": None,
                    "type": "none",
                    "severity": "none",
                    "evidence": data.get("summary", "No findings reported."),
                    "recommendation": "No action required.",
                    "source_status": status,
                }
            )

    return findings


def normalize_finding(file_path: str, finding: dict[str, Any], source_status: str) -> dict[str, Any]:
    severity = str(finding.get("severity") or "low").lower()
    if severity not in SEVERITIES:
        severity = "low"
    return {
        "file": file_path,
        "line": finding.get("line"),
        "type": str(finding.get("type") or "unknown"),
        "severity": severity,
        "evidence": str(finding.get("evidence") or ""),
        "recommendation": str(finding.get("recommendation") or ""),
        "source_status": source_status,
    }


def group_findings_by_severity(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {severity: [] for severity in SEVERITIES}
    for finding in findings:
        severity = finding.get("severity", "low")
        grouped[severity if severity in grouped else "low"].append(finding)
    return grouped


def group_findings_by_key(findings: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[str(finding.get(key) or "unknown")].append(finding)
    return dict(sorted(grouped.items()))


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
                "summary": data.get("summary", ""),
            }
        )
    return files


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
                "errors": result.get("errors", []),
            }
        )
    return failed


def build_summary(totals: dict[str, int], grouped_by_severity: dict[str, list[dict[str, Any]]]) -> str:
    actionable = totals["findings_total"]
    failed = totals["json_failed"]
    reused = totals["files_reused_from_memory"]
    return (
        f"Audit reduced {totals['files_analyzed']} analyzed files with {actionable} actionable findings, "
        f"{reused} reused results, and {failed} JSON failures."
    )


def build_recommendations(
    totals: dict[str, int],
    grouped_by_severity: dict[str, list[dict[str, Any]]],
) -> list[str]:
    recommendations = []
    if grouped_by_severity["critical"] or grouped_by_severity["high"]:
        recommendations.append("Review critical and high findings before lower priority cleanup.")
    if totals["json_failed"]:
        recommendations.append("Rerun failed JSON tasks or inspect their raw model output before final decisions.")
    if totals["files_reused_from_memory"]:
        recommendations.append("Reused results were included; rescan when source files change.")
    if not recommendations:
        recommendations.append("No urgent action was detected in the analyzed files.")
    return recommendations


def detect_profile(inputs: AuditInputs) -> str:
    return str(
        inputs.scan_result.get("profile_detected")
        or inputs.tasks_data.get("profile")
        or inputs.task_results.get("profile")
        or "general"
    )


def graphify_summary(inputs: AuditInputs) -> dict[str, Any]:
    graphify = inputs.graphify or inputs.tasks_data.get("graphify") or {}
    return {
        "detected": bool(graphify.get("detected")),
        "used": bool(graphify.get("used")),
        "nodes_total": int(graphify.get("nodes_total", 0)),
        "candidate_files": list(graphify.get("candidate_files", [])),
        "artifacts": dict(graphify.get("artifacts", {})),
    }


def load_model_profiles(memory_path: Path | str = DEFAULT_MEMORY_PATH) -> list[dict[str, Any]]:
    db_path = Path(memory_path)
    if not db_path.exists():
        return []
    memory = SQLiteMemory(db_path)
    return [asdict(profile) for profile in memory.list_model_profiles()]


def count_analyzed_files(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result.get("status") in {"completed", "reused"})


def count_reused_results(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result.get("status") == "reused")


def count_json_valid(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result.get("json_valid") is True)


def count_json_repaired(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result.get("json_repaired") is True)


def count_json_failed(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result.get("json_valid") is not True)


def count_actionable_findings(findings: list[dict[str, Any]]) -> int:
    return sum(1 for finding in findings if finding.get("severity") != "none")


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
