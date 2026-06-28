from datetime import datetime
import json

from governor.report_writer import render_markdown_report, write_audit_reports


def sample_report():
    return {
        "metadata": {
            "generated_at": "2026-06-22T00:00:00+00:00",
            "project_path": "/project",
            "profile_detected": "python",
            "model_used": "demo-model",
            "deterministic": True,
        },
        "summary": "Reduced 2 processed tasks with 1 actionable findings.",
        "counts": {
            "tasks_processed": 2,
            "results_reused": 1,
            "files_reused_from_memory": 1,
            "graph_enhanced_tasks": 1,
            "json_valid": 1,
            "json_repaired": 1,
            "json_failed": 1,
            "truncated_files": 1,
        },
        "findings": {
            "all": [
                {
                    "file": "src/a.py",
                    "line": 4,
                    "type": "security",
                    "risk": "high",
                    "severity": "high",
                    "evidence": "Unsafe call.",
                    "recommendation": "Validate inputs.",
                }
            ],
            "by_risk": {
                "critical": [],
                "high": [{"file": "src/a.py"}],
                "medium": [],
                "low": [],
                "none": [],
            },
            "by_file": {"src/a.py": [{"type": "security"}]},
            "by_type": {"security": [{"file": "src/a.py"}]},
        },
        "graphify": {
            "detected": True,
            "nodes": 3,
            "edges": 4,
            "graph_enhanced_tasks": 1,
            "important_files": ["src/a.py"],
            "warnings": ["Graphify referenced a missing path: config/prod.json"],
        },
        "task_statuses": {"completed": 1, "reused": 1, "failed_json": 1},
        "json_quality": {"valid": 1, "repaired": 1, "failed": 1},
        "failed_tasks": [{"file": "src/b.py", "status": "failed_json", "errors": ["bad json"]}],
        "reused_results": [{"file": "src/c.py", "task_id": "task-0003"}],
        "truncated_files": [{"file": "src/a.py", "task_id": "task-0001"}],
        "recommendations": ["Review critical and high findings before lower priority cleanup."],
        "limitations": ["This report is generated deterministically from task_results.json."],
        "report_paths": {"markdown": "", "json": ""},
    }


def test_render_markdown_report_includes_required_sections():
    markdown = render_markdown_report(sample_report())

    assert "# LocalScope Audit" in markdown
    assert "Fecha: 2026-06-22T00:00:00+00:00" in markdown
    assert "## Resumen ejecutivo" in markdown
    assert "Perfil detectado: python" in markdown
    assert "Modelo usado: demo-model" in markdown
    assert "Tareas procesadas: 2" in markdown
    assert "Resultados reutilizados desde memoria: 1" in markdown
    assert "JSON validos: 1" in markdown
    assert "JSON reparados: 1" in markdown
    assert "JSON fallidos: 1" in markdown
    assert "Archivos truncados: 1" in markdown
    assert "Tareas mejoradas por Graphify: 1" in markdown
    assert "## Graphify" in markdown
    assert "Graphify detected: yes" in markdown
    assert "Graph nodes: 3" in markdown
    assert "Graph edges: 4" in markdown
    assert "- src/a.py" in markdown
    assert "Graphify referenced a missing path" in markdown
    assert "## Hallazgos por riesgo" in markdown
    assert "| Riesgo | Archivo | Linea | Tipo | Evidencia | Recomendacion |" in markdown
    assert "## Recomendaciones generales" in markdown
    assert "## Limitaciones" in markdown


def test_write_audit_reports_uses_timestamped_names_and_writes_paths(tmp_path):
    report = sample_report()
    markdown_path, json_path = write_audit_reports(
        report,
        output_dir=tmp_path,
        timestamp=datetime(2026, 6, 21, 15, 30, 45),
    )

    assert markdown_path.name == "audit-20260621-153045.md"
    assert json_path.name == "audit-20260621-153045.json"
    assert markdown_path.exists()
    assert json_path.exists()

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["metadata"]["profile_detected"] == "python"
    assert written["report_paths"]["markdown"] == str(markdown_path)
    assert written["report_paths"]["json"] == str(json_path)
    assert report["report_paths"]["markdown"] == str(markdown_path)


def test_render_markdown_report_marks_graphify_absent():
    report = sample_report()
    report["graphify"] = {"detected": False, "nodes": 0, "edges": 0, "graph_enhanced_tasks": 0}
    report["counts"]["graph_enhanced_tasks"] = 0

    markdown = render_markdown_report(report)

    assert "Graphify detected: no" in markdown
    assert "Graph-enhanced tasks: 0" in markdown
