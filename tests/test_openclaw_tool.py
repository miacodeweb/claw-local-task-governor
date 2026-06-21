import json
from pathlib import Path

import pytest

from governor.ollama_client import OllamaConfig
from governor.main import main
from governor.openclaw_tool import local_audit_report, local_audit_status, local_project_audit


class FakeClient:
    def __init__(self, responses):
        self.config = OllamaConfig(model="demo-model", max_chars_per_file=1000)
        self.responses = list(responses)
        self.calls = []

    def analyze_text_with_model(self, prompt, text):
        self.calls.append({"prompt": prompt, "text": text})
        return self.responses.pop(0)


def valid_model_json(file_path):
    return json.dumps(
        {
            "file": file_path,
            "status": "ok",
            "risk": "none",
            "summary": "No clear issues found.",
            "findings": [],
            "needs_related_file": False,
            "related_files": [],
        }
    )


def write_audit_report(output_dir, name="audit-20260621-153045"):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "completed",
        "summary": "Audit reduced 1 analyzed files with 0 actionable findings.",
        "profile_detected": "python",
        "totals": {
            "files_scanned": 2,
            "files_analyzed": 1,
            "files_reused_from_memory": 0,
            "json_valid": 1,
            "json_repaired": 0,
            "json_failed": 0,
        },
        "findings_by_priority": {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "none": [{"file": "main.py"}],
        },
        "failed_tasks": [],
        "recommendations": ["No urgent action was detected in the analyzed files."],
    }
    json_path = output_dir / f"{name}.json"
    markdown_path = output_dir / f"{name}.md"
    json_path.write_text(json.dumps(report), encoding="utf-8")
    markdown_path.write_text("# report\n", encoding="utf-8")
    return markdown_path, json_path


def test_local_project_audit_runs_high_level_read_only_flow(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    client = FakeClient([valid_model_json("main.py")])

    response = local_project_audit(
        path=project,
        profile="auto",
        mode="general",
        max_files=1,
        read_only=True,
        output_dir=output_dir,
        client=client,
    )

    assert response["status"] == "completed"
    assert response["files_scanned"] == 1
    assert response["files_analyzed"] == 1
    assert response["files_reused_from_memory"] == 0
    assert response["json_valid"] == 1
    assert response["json_repaired"] == 0
    assert response["json_failed"] == 0
    assert (output_dir / "scan_result.json").exists()
    assert (output_dir / "tasks.json").exists()
    assert (output_dir / "task_results.json").exists()
    assert response["report_path"].endswith(".md")
    assert len(client.calls) == 1


def test_local_project_audit_rejects_non_read_only_requests(tmp_path):
    output_dir = tmp_path / "reports"

    response = local_project_audit(
        path=tmp_path / "missing-project",
        read_only=False,
        output_dir=output_dir,
    )

    assert response["status"] == "rejected"
    assert response["files_scanned"] == 0
    assert not output_dir.exists()


def test_local_project_audit_validates_public_arguments(tmp_path):
    with pytest.raises(ValueError):
        local_project_audit(path=tmp_path, profile="rails")

    with pytest.raises(ValueError):
        local_project_audit(path=tmp_path, mode="rewrite")

    with pytest.raises(ValueError):
        local_project_audit(path=tmp_path, max_files=0)


def test_local_audit_status_returns_recent_audits_without_reanalysis(tmp_path):
    output_dir = tmp_path / "reports"
    markdown_path, json_path = write_audit_report(output_dir)
    (output_dir / "task_results.json").write_text(
        json.dumps(
            {
                "project_path": "/project",
                "generated_at": "2026-06-21T15:30:45+00:00",
                "tasks_selected": 1,
                "tasks_completed": 1,
                "tasks_failed": 0,
                "tasks_reused": 0,
            }
        ),
        encoding="utf-8",
    )

    response = local_audit_status(output_dir=output_dir)

    assert response["status"] == "completed"
    assert response["audits_count"] == 1
    assert response["recent_audits"][0]["report_path"] == str(markdown_path.resolve())
    assert response["recent_audits"][0]["json_report_path"] == str(json_path.resolve())
    assert response["recent_audits"][0]["files_analyzed"] == 1
    assert response["current_task_results"]["tasks_completed"] == 1


def test_local_audit_status_handles_empty_output_dir(tmp_path):
    response = local_audit_status(output_dir=tmp_path / "reports")

    assert response["status"] == "no_audits"
    assert response["audits_count"] == 0
    assert response["recent_audits"] == []
    assert response["current_task_results"] == {}


def test_local_audit_report_returns_compact_summary_from_json_or_markdown(tmp_path):
    markdown_path, json_path = write_audit_report(tmp_path / "reports")

    json_response = local_audit_report(report_path=json_path)
    markdown_response = local_audit_report(report_path=markdown_path)

    assert json_response["status"] == "completed"
    assert json_response["report_path"] == str(markdown_path.resolve())
    assert json_response["json_report_path"] == str(json_path.resolve())
    assert json_response["files_scanned"] == 2
    assert json_response["findings_by_priority"]["none"] == 1
    assert markdown_response == json_response


def test_openclaw_manifest_exposes_high_level_tools_only():
    manifest = json.loads(
        (Path(__file__).parents[1] / "openclaw" / "tool_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert [tool["name"] for tool in manifest["tools"]] == [
        "local_project_audit",
        "local_audit_status",
        "local_audit_report",
    ]
    for tool in manifest["tools"]:
        assert tool["safety"]["read_only"] is True
        assert tool["safety"]["allows_editing"] is False
    assert "read_file" not in json.dumps(manifest)
    assert "write_file" not in json.dumps(manifest)


def test_openclaw_audit_cli_prints_json_response(monkeypatch, capsys, tmp_path):
    def fake_local_project_audit(**kwargs):
        assert kwargs["path"] == tmp_path
        assert kwargs["profile"] == "auto"
        assert kwargs["mode"] == "general"
        assert kwargs["max_files"] == 3
        assert kwargs["read_only"] is True
        return {
            "status": "completed",
            "report_path": "reports/audit.md",
            "summary": "ok",
            "files_scanned": 1,
            "files_analyzed": 1,
            "files_reused_from_memory": 0,
            "json_valid": 1,
            "json_repaired": 0,
            "json_failed": 0,
        }

    monkeypatch.setattr("governor.main.local_project_audit", fake_local_project_audit)

    exit_code = main(
        [
            "openclaw-audit",
            "--path",
            str(tmp_path),
            "--max-files",
            "3",
            "--read-only",
            "true",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["report_path"] == "reports/audit.md"


def test_openclaw_status_cli_prints_json_response(monkeypatch, capsys, tmp_path):
    def fake_local_audit_status(**kwargs):
        assert kwargs["output_dir"] == tmp_path
        assert kwargs["limit"] == 2
        return {
            "status": "completed",
            "output_dir": str(tmp_path),
            "audits_count": 1,
            "recent_audits": [{"status": "completed"}],
            "current_task_results": {},
        }

    monkeypatch.setattr("governor.main.local_audit_status", fake_local_audit_status)

    exit_code = main(["openclaw-status", "--output-dir", str(tmp_path), "--limit", "2"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["audits_count"] == 1


def test_openclaw_report_cli_prints_json_response(monkeypatch, capsys, tmp_path):
    report_path = tmp_path / "audit.json"

    def fake_local_audit_report(**kwargs):
        assert kwargs["report_path"] == report_path
        return {
            "status": "completed",
            "report_path": str(report_path.with_suffix(".md")),
            "json_report_path": str(report_path),
            "summary": "ok",
        }

    monkeypatch.setattr("governor.main.local_audit_report", fake_local_audit_report)

    exit_code = main(["openclaw-report", "--report-path", str(report_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["summary"] == "ok"
