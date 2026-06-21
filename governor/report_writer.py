"""Write deterministic Markdown and JSON audit reports."""

from __future__ import annotations

import json
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

    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return markdown_path, json_path


def render_markdown_report(report: dict[str, Any]) -> str:
    totals = report.get("totals", {})
    lines = [
        "# Claw Local Task Governor Audit",
        "",
        "## Resumen ejecutivo",
        report.get("summary", "Audit report generated."),
        "",
        "## Metricas",
        f"- Perfil detectado: {report.get('profile_detected', 'general')}",
        f"- Graphify detectado: {yes_no(report.get('graphify', {}).get('detected', False))}",
        f"- Graphify usado: {yes_no(report.get('graphify', {}).get('used', False))}",
        f"- Nodos Graphify relevantes: {report.get('graphify', {}).get('nodes_total', 0)}",
        f"- Archivos escaneados: {totals.get('files_scanned', 0)}",
        f"- Archivos analizados: {totals.get('files_analyzed', 0)}",
        f"- Resultados reutilizados desde memoria: {totals.get('files_reused_from_memory', 0)}",
        f"- JSON validos: {totals.get('json_valid', 0)}",
        f"- JSON reparados: {totals.get('json_repaired', 0)}",
        f"- JSON fallidos: {totals.get('json_failed', 0)}",
        "",
        "## Perfil operativo de modelos",
    ]

    model_profiles = report.get("model_profiles", [])
    if not model_profiles:
        lines.append("- Sin estadisticas de modelos todavia.")
    else:
        for profile in model_profiles:
            lines.append(
                f"- {profile.get('model', 'unknown')} / {profile.get('task_type', 'unknown')}: "
                f"{profile.get('success_count', 0)} exitos, "
                f"{profile.get('json_fail_count', 0)} fallos JSON, "
                f"{profile.get('json_repair_count', 0)} reparados, "
                f"{float(profile.get('average_response_time', 0)):.2f}s promedio, "
                f"{profile.get('recommended_max_chars', 0)} chars recomendados"
            )

    lines.extend(
        [
            "",
            "## Hallazgos por prioridad",
        ]
    )

    findings_by_priority = report.get("findings_by_priority", {})
    for severity in SEVERITIES:
        findings = findings_by_priority.get(severity, [])
        lines.append(f"### {severity}")
        if not findings:
            lines.append("- Sin hallazgos.")
            lines.append("")
            continue

        for finding in findings:
            line_text = "" if finding.get("line") is None else f":{finding.get('line')}"
            lines.append(
                f"- {finding.get('file', 'unknown')}{line_text} "
                f"[{finding.get('type', 'unknown')}]: {finding.get('evidence', '')} "
                f"Recomendacion: {finding.get('recommendation', '')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Agrupado por archivo",
        ]
    )
    for file_path, findings in report.get("findings_by_file", {}).items():
        lines.append(f"- {file_path}: {len(findings)} hallazgo(s)")

    lines.extend(
        [
            "",
            "## Agrupado por tipo",
        ]
    )
    for finding_type, findings in report.get("findings_by_type", {}).items():
        lines.append(f"- {finding_type}: {len(findings)} hallazgo(s)")

    failed_tasks = report.get("failed_tasks", [])
    if failed_tasks:
        lines.extend(["", "## Tareas fallidas"])
        for task in failed_tasks:
            errors = "; ".join(str(error) for error in task.get("errors", []))
            lines.append(f"- {task.get('file', 'unknown')} [{task.get('status', 'failed')}]: {errors}")

    lines.extend(["", "## Recomendaciones generales"])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")

    lines.append("")
    return "\n".join(lines)


def yes_no(value: bool) -> str:
    return "si" if value else "no"
