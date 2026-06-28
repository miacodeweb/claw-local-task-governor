import json

import pytest

from governor.reducer import AuditInputs, build_final_report, load_audit_inputs


def completed_result(file_path, findings=None, *, status="completed", truncated=False):
    findings = findings if findings is not None else []
    risk = findings[0]["severity"] if findings else "none"
    return {
        "task_id": f"task-{file_path}",
        "file_path": file_path,
        "file_hash": "hash",
        "task_type": "inspect_code_file",
        "profile": "python",
        "status": status,
        "json_valid": True,
        "json_repaired": False,
        "truncated": truncated,
        "model": "demo-model",
        "raw_response": "{}",
        "result": {
            "file": file_path,
            "status": "needs_review" if findings else "ok",
            "risk": risk,
            "summary": "Summary.",
            "findings": findings,
            "needs_related_file": False,
            "related_files": [],
        },
        "errors": [],
        "created_at": "2026-06-22T00:00:00+00:00",
    }


def failed_result(file_path):
    return {
        "task_id": "task-failed",
        "file_path": file_path,
        "file_hash": "hash",
        "task_type": "inspect_code_file",
        "profile": "python",
        "status": "failed_json",
        "json_valid": False,
        "json_repaired": False,
        "truncated": False,
        "model": "demo-model",
        "raw_response": "not-json",
        "result": None,
        "errors": ["missing required field"],
        "created_at": "2026-06-22T00:00:00+00:00",
    }


def make_inputs(results, *, tasks_data=None):
    return AuditInputs(
        project_path="/project",
        scan_result={"profile_detected": "python", "files_found": 10, "relevant_files": 4},
        tasks_data=tasks_data or {"tasks_total": len(results), "profile": "python"},
        task_results={
            "tasks_requested": len(results),
            "tasks_selected": len(results),
            "tasks_processed": len(results),
            "results": results,
        },
        results_path="reports/task_results.json",
    )


def test_build_final_report_groups_findings_and_counts_failures():
    report = build_final_report(
        make_inputs(
            [
                completed_result(
                    "src/a.py",
                    [
                        {
                            "line": 7,
                            "type": "security",
                            "severity": "high",
                            "evidence": "Unsafe call.",
                            "recommendation": "Validate inputs.",
                        }
                    ],
                ),
                completed_result("src/b.py", status="reused"),
                failed_result("src/c.py"),
            ]
        )
    )

    assert report["metadata"]["profile_detected"] == "python"
    assert report["metadata"]["model_used"] == "demo-model"
    assert report["status"] == "completed_with_errors"
    assert report["counts"]["tasks_processed"] == 3
    assert report["counts"]["files_analyzed"] == 2
    assert report["counts"]["results_reused"] == 1
    assert report["counts"]["json_valid"] == 2
    assert report["counts"]["json_failed"] == 1
    assert report["counts"]["findings_total"] == 1
    assert len(report["findings"]["by_risk"]["high"]) == 1
    assert len(report["findings"]["by_risk"]["none"]) == 1
    assert "src/a.py" in report["findings"]["by_file"]
    assert "security" in report["findings"]["by_type"]
    assert report["failed_tasks"][0]["file"] == "src/c.py"
    assert report["reused_results"][0]["file"] == "src/b.py"


def test_build_final_report_without_findings_has_none_group():
    report = build_final_report(make_inputs([completed_result("src/clean.py")]))

    assert report["status"] == "completed"
    assert report["counts"]["findings_total"] == 0
    assert report["counts"]["none"] == 1
    assert len(report["findings"]["by_risk"]["none"]) == 1
    assert report["recommendations"] == ["No urgent action was detected in the analyzed files."]


def test_build_final_report_counts_json_failed_tasks():
    report = build_final_report(make_inputs([failed_result("src/bad.py")]))

    assert report["status"] == "completed_with_errors"
    assert report["counts"]["json_failed"] == 1
    assert report["json_quality"]["failed"] == 1
    assert report["failed_tasks"][0]["errors"] == ["missing required field"]


def test_build_final_report_counts_reused_results():
    report = build_final_report(make_inputs([completed_result("src/reused.py", status="reused")]))

    assert report["counts"]["results_reused"] == 1
    assert report["counts"]["files_reused_from_memory"] == 1
    assert report["task_statuses"]["reused"] == 1
    assert report["reused_results"][0]["file"] == "src/reused.py"


def test_build_final_report_counts_truncated_files():
    report = build_final_report(make_inputs([completed_result("src/large.py", truncated=True)]))

    assert report["counts"]["truncated_files"] == 1
    assert report["truncated_files"][0]["file"] == "src/large.py"
    assert any("truncated" in item for item in report["limitations"])


def test_load_audit_inputs_requires_task_results(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_audit_inputs(tmp_path / "project", output_dir=tmp_path / "reports")


def test_load_audit_inputs_accepts_custom_results_path(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    results_path = tmp_path / "custom-results.json"
    results_path.write_text(json.dumps({"results": []}), encoding="utf-8")

    inputs = load_audit_inputs(project, output_dir=tmp_path / "reports", results_path=results_path)

    assert inputs.results_path == str(results_path)
    assert inputs.task_results == {"results": []}


def test_build_final_report_includes_graphify_context():
    tasks_data = {
        "tasks_total": 1,
        "profile": "python",
        "graphify": {
            "detected": True,
            "used": True,
            "graph_path": "/project/graphify-out/graph.json",
            "nodes_total": 3,
            "edges_total": 4,
            "candidate_files": ["src/core.py"],
            "important_files": ["src/core.py"],
            "central_nodes": [{"path": "src/core.py"}],
            "high_connectivity_files": ["src/core.py"],
            "communities": [{"id": "backend", "files": ["src/core.py"]}],
            "warnings": ["Graphify referenced a missing path: config/prod.json"],
        },
        "tasks": [
            {
                "task_id": "task-0001",
                "file_path": "src/core.py",
                "reason": "scanner: source_code; graphify: central_node",
            }
        ],
    }

    report = build_final_report(make_inputs([completed_result("src/core.py")], tasks_data=tasks_data))

    assert report["graphify"]["detected"] is True
    assert report["graphify"]["nodes"] == 3
    assert report["graphify"]["edges"] == 4
    assert report["graphify"]["graph_enhanced_tasks"] == 1
    assert report["counts"]["graph_enhanced_tasks"] == 1
    assert report["graphify"]["important_files"] == ["src/core.py"]


def test_build_final_report_marks_graphify_absent_by_default():
    report = build_final_report(make_inputs([completed_result("src/clean.py")]))

    assert report["graphify"]["detected"] is False
    assert report["graphify"]["nodes"] == 0
    assert report["counts"]["graph_enhanced_tasks"] == 0
