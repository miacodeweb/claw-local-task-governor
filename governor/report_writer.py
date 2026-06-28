"""Write deterministic Markdown and JSON audit reports."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from governor.reducer import SEVERITIES


def write_audit_reports(
    report: dict[str, Any],
    output_dir: Path | str = "reports",
    timestamp: datetime | None = None,
) -> tuple[Path, Path]:
    """Write audit-YYYYMMDD-HHMMSS.md and .json reports."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S")
    markdown_path = output_path / f"audit-{stamp}.md"
    json_path = output_path / f"audit-{stamp}.json"

    report_to_write = deepcopy(report)
    report_to_write["report_paths"] = {
        "markdown": str(markdown_path),
        "json": str(json_path),
    }

    markdown_path.write_text(render_markdown_report(report_to_write), encoding="utf-8")
    json_path.write_text(json.dumps(report_to_write, indent=2), encoding="utf-8")
    report["report_paths"] = dict(report_to_write["report_paths"])
    return markdown_path, json_path


def render_markdown_report(report: dict[str, Any]) -> str:
    metadata = report.get("metadata", {})
    counts = report.get("counts", report.get("totals", {}))
    findings = report.get("findings", {})
    findings_by_risk = findings.get("by_risk", report.get("findings_by_priority", {}))
    all_findings = list(findings.get("all", []))
    failed_tasks = list(report.get("failed_tasks", []))
    reused_results = list(report.get("reused_results", []))
    truncated_files = list(report.get("truncated_files", []))
    graphify = report.get("graphify", report.get("graphify_context", {}))

    lines = [
        "# LocalScope Audit",
        "",
        f"Fecha: {metadata.get('generated_at', 'unknown')}",
        "",
        "## Resumen ejecutivo",
        str(report.get("summary", "Audit report generated.")),
        "",
        "## Metricas",
        f"- Perfil detectado: {metadata.get('profile_detected', report.get('profile_detected', 'general'))}",
        f"- Modelo usado: {metadata.get('model_used', report.get('model_used', 'unknown'))}",
        f"- Tareas procesadas: {counts.get('tasks_processed', 0)}",
        f"- Resultados reutilizados desde memoria: {counts.get('results_reused', counts.get('files_reused_from_memory', 0))}",
        f"- JSON validos: {counts.get('json_valid', 0)}",
        f"- JSON reparados: {counts.get('json_repaired', 0)}",
        f"- JSON fallidos: {counts.get('json_failed', 0)}",
        f"- Archivos truncados: {counts.get('truncated_files', 0)}",
        f"- Tareas mejoradas por Graphify: {counts.get('graph_enhanced_tasks', graphify.get('graph_enhanced_tasks', 0))}",
        "",
        "## Graphify",
        f"- Graphify detected: {'yes' if graphify.get('detected') else 'no'}",
        f"- Graph nodes: {graphify.get('nodes', 0)}",
        f"- Graph edges: {graphify.get('edges', 0)}",
        f"- Graph-enhanced tasks: {graphify.get('graph_enhanced_tasks', 0)}",
        "",
        "### Important files from graph",
    ]

    important_files = list(graphify.get("important_files", []))
    if important_files:
        for file_path in important_files[:20]:
            lines.append(f"- {file_path}")
    else:
        lines.append("- None.")

    graphify_warnings = list(graphify.get("warnings", []))
    if graphify_warnings:
        lines.extend(["", "### Graphify warnings"])
        for warning in graphify_warnings[:20]:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
        "## Hallazgos por riesgo",
        ]
    )

    for risk in SEVERITIES:
        lines.append(f"- {risk}: {len(findings_by_risk.get(risk, []))}")

    lines.extend(["", "## Tabla de hallazgos"])
    if all_findings:
        lines.extend(
            [
                "| Riesgo | Archivo | Linea | Tipo | Evidencia | Recomendacion |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for finding in all_findings:
            if finding.get("risk") == "none":
                continue
            lines.append(
                "| {risk} | {file} | {line} | {type} | {evidence} | {recommendation} |".format(
                    risk=escape_cell(finding.get("risk", "")),
                    file=escape_cell(finding.get("file", "")),
                    line=escape_cell("" if finding.get("line") is None else finding.get("line")),
                    type=escape_cell(finding.get("type", "")),
                    evidence=escape_cell(finding.get("evidence", "")),
                    recommendation=escape_cell(finding.get("recommendation", "")),
                )
            )
        if not any(finding.get("risk") != "none" for finding in all_findings):
            lines.append("| none | - | - | none | No actionable findings. | No action required. |")
    else:
        lines.append("Sin hallazgos.")

    lines.extend(["", "## Agrupado por archivo"])
    for file_path, file_findings in findings.get("by_file", report.get("findings_by_file", {})).items():
        lines.append(f"- {file_path}: {len(file_findings)} hallazgo(s)")
    if not findings.get("by_file", report.get("findings_by_file", {})):
        lines.append("- Sin datos.")

    lines.extend(["", "## Agrupado por tipo"])
    for finding_type, type_findings in findings.get("by_type", report.get("findings_by_type", {})).items():
        lines.append(f"- {finding_type}: {len(type_findings)} hallazgo(s)")
    if not findings.get("by_type", report.get("findings_by_type", {})):
        lines.append("- Sin datos.")

    lines.extend(["", "## Estado de tareas"])
    for status, count in report.get("task_statuses", {}).items():
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## Calidad JSON"])
    for status, count in report.get("json_quality", {}).items():
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## Resultados reutilizados"])
    if reused_results:
        for item in reused_results:
            lines.append(f"- {item.get('file', '')} ({item.get('task_id', '')})")
    else:
        lines.append("- Ninguno.")

    lines.extend(["", "## Archivos truncados"])
    if truncated_files:
        for item in truncated_files:
            lines.append(f"- {item.get('file', '')} ({item.get('task_id', '')})")
    else:
        lines.append("- Ninguno.")

    if failed_tasks:
        lines.extend(["", "## Tareas fallidas"])
        for task in failed_tasks:
            errors = "; ".join(str(error) for error in task.get("errors", []))
            lines.append(f"- {task.get('file', 'unknown')} [{task.get('status', 'failed')}]: {errors}")

    lines.extend(["", "## Recomendaciones generales"])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")

    lines.extend(["", "## Limitaciones"])
    for limitation in report.get("limitations", []):
        lines.append(f"- {limitation}")

    lines.append("")
    return "\n".join(lines)


def escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()
