from governor.reducer import AuditInputs, build_final_report


def test_build_final_report_groups_findings_and_counts_failures():
    inputs = AuditInputs(
        project_path="/project",
        scan_result={"profile_detected": "python", "files_found": 10, "relevant_files": 4},
        tasks_data={"tasks_total": 3, "profile": "python"},
        task_results={
            "tasks_selected": 3,
            "results": [
                {
                    "task_id": "task-0001",
                    "file_path": "src/a.py",
                    "status": "completed",
                    "json_valid": True,
                    "json_repaired": False,
                    "risk": "high",
                    "result": {
                        "file": "src/a.py",
                        "status": "needs_review",
                        "risk": "high",
                        "summary": "High issue.",
                        "findings": [
                            {
                                "line": 7,
                                "type": "security",
                                "severity": "high",
                                "evidence": "Unsafe call.",
                                "recommendation": "Validate inputs.",
                            }
                        ],
                        "needs_related_file": False,
                        "related_files": [],
                    },
                },
                {
                    "task_id": "task-0002",
                    "file_path": "src/b.py",
                    "status": "reused",
                    "json_valid": True,
                    "json_repaired": True,
                    "risk": "none",
                    "result": {
                        "file": "src/b.py",
                        "status": "ok",
                        "risk": "none",
                        "summary": "Clean.",
                        "findings": [],
                        "needs_related_file": False,
                        "related_files": [],
                    },
                },
                {
                    "task_id": "task-0003",
                    "file_path": "src/c.py",
                    "status": "failed_json",
                    "json_valid": False,
                    "json_repaired": False,
                    "risk": "none",
                    "result": None,
                    "errors": ["missing required field"],
                },
            ],
        },
        model_profiles=[
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
    )

    report = build_final_report(inputs)

    assert report["profile_detected"] == "python"
    assert report["graphify"]["detected"] is False
    assert report["status"] == "completed_with_errors"
    assert report["totals"]["files_scanned"] == 10
    assert report["totals"]["files_analyzed"] == 2
    assert report["totals"]["files_reused_from_memory"] == 1
    assert report["totals"]["json_valid"] == 2
    assert report["totals"]["json_repaired"] == 1
    assert report["totals"]["json_failed"] == 1
    assert report["totals"]["findings_total"] == 1
    assert len(report["findings_by_priority"]["high"]) == 1
    assert len(report["findings_by_priority"]["none"]) == 1
    assert "src/a.py" in report["findings_by_file"]
    assert "security" in report["findings_by_type"]
    assert report["failed_tasks"][0]["file"] == "src/c.py"
    assert report["model_profiles"][0]["recommended_max_chars"] == 8000


def test_build_final_report_handles_empty_results():
    report = build_final_report(
        AuditInputs(
            project_path="/project",
            scan_result={},
            tasks_data={},
            task_results={},
        )
    )

    assert report["status"] == "completed"
    assert report["profile_detected"] == "general"
    assert report["totals"]["files_analyzed"] == 0
    assert report["recommendations"] == ["No urgent action was detected in the analyzed files."]


def test_build_final_report_includes_graphify_metadata():
    report = build_final_report(
        AuditInputs(
            project_path="/project",
            scan_result={"profile_detected": "python"},
            tasks_data={},
            task_results={},
            graphify={
                "detected": True,
                "used": True,
                "nodes_total": 2,
                "candidate_files": ["src/main.py"],
                "artifacts": {"graph_json": "/project/graphify-out/graph.json"},
            },
        )
    )

    assert report["graphify"]["detected"] is True
    assert report["graphify"]["used"] is True
    assert report["graphify"]["nodes_total"] == 2
    assert report["graphify"]["candidate_files"] == ["src/main.py"]
