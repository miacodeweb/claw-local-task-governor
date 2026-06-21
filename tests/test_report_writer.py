from datetime import datetime
import json

from governor.report_writer import render_markdown_report, write_audit_reports


def sample_report():
    return {
        "status": "completed_with_errors",
        "project_path": "/project",
        "profile_detected": "python",
        "graphify": {"detected": True, "used": True, "nodes_total": 2},
        "summary": "Audit reduced 1 analyzed files with 1 actionable findings.",
        "totals": {
            "files_scanned": 3,
            "files_analyzed": 1,
            "files_reused_from_memory": 1,
            "json_valid": 1,
            "json_repaired": 1,
            "json_failed": 1,
        },
        "findings_by_priority": {
            "critical": [],
            "high": [
                {
                    "file": "src/a.py",
                    "line": 4,
                    "type": "security",
                    "severity": "high",
                    "evidence": "Unsafe call.",
                    "recommendation": "Validate inputs.",
                }
            ],
            "medium": [],
            "low": [],
            "none": [],
        },
        "findings_by_file": {"src/a.py": [{"type": "security"}]},
        "findings_by_type": {"security": [{"file": "src/a.py"}]},
        "model_profiles": [
            {
                "model": "demo-model",
                "task_type": "inspect_code_file",
                "success_count": 2,
                "json_fail_count": 1,
                "json_repair_count": 1,
                "average_response_time": 1.25,
                "recommended_max_chars": 8000,
                "updated_at": "2026-06-21T00:00:00+00:00",
            }
        ],
        "failed_tasks": [{"file": "src/b.py", "status": "failed_json", "errors": ["bad json"]}],
        "recommendations": ["Review critical and high findings before lower priority cleanup."],
    }


def test_render_markdown_report_includes_required_sections():
    markdown = render_markdown_report(sample_report())

    assert "## Resumen ejecutivo" in markdown
    assert "Perfil detectado: python" in markdown
    assert "Graphify detectado: si" in markdown
    assert "Graphify usado: si" in markdown
    assert "Nodos Graphify relevantes: 2" in markdown
    assert "Archivos escaneados: 3" in markdown
    assert "Archivos analizados: 1" in markdown
    assert "Resultados reutilizados desde memoria: 1" in markdown
    assert "JSON validos: 1" in markdown
    assert "JSON reparados: 1" in markdown
    assert "JSON fallidos: 1" in markdown
    assert "## Perfil operativo de modelos" in markdown
    assert "demo-model / inspect_code_file" in markdown
    assert "8000 chars recomendados" in markdown
    assert "## Hallazgos por prioridad" in markdown
    assert "## Recomendaciones generales" in markdown


def test_write_audit_reports_uses_timestamped_names(tmp_path):
    markdown_path, json_path = write_audit_reports(
        sample_report(),
        output_dir=tmp_path,
        timestamp=datetime(2026, 6, 21, 15, 30, 45),
    )

    assert markdown_path.name == "audit-20260621-153045.md"
    assert json_path.name == "audit-20260621-153045.json"
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["profile_detected"] == "python"
