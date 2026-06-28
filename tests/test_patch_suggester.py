import json
from pathlib import Path

import pytest

from governor.main import main
from governor.ollama_client import OllamaConfig, OllamaConnectionError
from governor.patch_suggester import PATCH_WARNING, suggest_patches
from tests.test_schemas import ValidationError, load_schema, validate


class FakeClient:
    def __init__(self, responses):
        self.config = OllamaConfig(model="demo-model", max_chars_per_file=1000)
        self.responses = list(responses)
        self.calls = []

    def analyze_text_with_model(self, prompt, text):
        self.calls.append({"prompt": prompt, "text": text})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def valid_patch_json(file_path="src/main.py"):
    return json.dumps(
        {
            "status": "suggested",
            "file_path": file_path,
            "finding_type": "code_quality",
            "severity": "high",
            "summary": "Rename the vague variable.",
            "diff": (
                f"--- a/{file_path}\n"
                f"+++ b/{file_path}\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+value = 1\n"
            ),
            "not_applied": True,
            "errors": [],
        }
    )


def write_audit_report(path, findings):
    report = {
        "metadata": {"project_path": "/project"},
        "findings": {
            "all": findings,
            "by_risk": {
                "critical": [],
                "high": findings,
                "medium": [],
                "low": [],
                "none": [],
            },
        },
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def write_task_results(path, file_path="src/main.py"):
    report = {
        "results": [
            {
                "file_path": file_path,
                "result": {
                    "file": file_path,
                    "findings": [finding(file_path)],
                },
            }
        ]
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def finding(file_path="src/main.py"):
    return {
        "file": file_path,
        "line": 1,
        "type": "code_quality",
        "severity": "high",
        "evidence": "Uses a vague name.",
        "recommendation": "Use a clearer name.",
    }


def make_project(tmp_path):
    project = tmp_path / "project"
    source = project / "src" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("x = 1\n", encoding="utf-8")
    return project, source


def test_suggest_patches_generates_markdown_and_json_without_modifying_project(tmp_path):
    project, source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding()])
    client = FakeClient([valid_patch_json()])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed"
    assert summary.mode == "suggest_patch"
    assert summary.patches_created == 1
    assert summary.patches_failed == 0
    assert summary.warning == PATCH_WARNING
    assert source.read_text(encoding="utf-8") == "x = 1\n"

    patch_dir = tmp_path / "reports" / "patches"
    markdown_files = list(patch_dir.glob("patch-*.md"))
    json_files = list(patch_dir.glob("patch-*.json"))
    assert len(markdown_files) == 1
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["status"] == "suggested"
    assert data["not_applied"] is True
    assert data["warning"] == PATCH_WARNING
    assert data["model"] == "demo-model"
    assert "--- a/src/main.py" in data["diff"]
    assert PATCH_WARNING in markdown_files[0].read_text(encoding="utf-8")
    assert "src/main.py" in client.calls[0]["prompt"]
    validate(data["status"] and {
        key: data[key]
        for key in (
            "status",
            "file_path",
            "finding_type",
            "severity",
            "summary",
            "diff",
            "not_applied",
            "errors",
        )
    }, load_schema("patch_suggestion.schema.json"))


def test_suggest_patches_can_read_task_results_json(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_task_results(tmp_path / "task_results.json")
    client = FakeClient([valid_patch_json()])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.patches_created == 1
    assert summary.suggestions[0].file_path == "src/main.py"


def test_suggest_patch_dry_run_does_not_call_ollama_or_write_outputs(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding()])
    client = FakeClient([valid_patch_json()])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        dry_run=True,
        client=client,
    )

    assert summary.status == "dry_run"
    assert summary.dry_run is True
    assert summary.candidates[0]["file_path"] == "src/main.py"
    assert summary.patches_created == 0
    assert client.calls == []
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_rejects_missing_report(tmp_path):
    project, _source = make_project(tmp_path)

    with pytest.raises(FileNotFoundError):
        suggest_patches(project, report_path=tmp_path / "missing.json")


def test_suggest_patches_rejects_file_outside_project(tmp_path):
    project, _source = make_project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    report_path = write_audit_report(tmp_path / "audit.json", [finding(str(outside))])
    client = FakeClient([valid_patch_json(str(outside))])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert "unsafe" in summary.suggestions[0].errors[0].lower()
    assert client.calls == []
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_rejects_path_traversal(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding("../outside.py")])
    client = FakeClient([])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert "unsafe project file path" in summary.suggestions[0].errors[0]
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_rejects_diff_for_another_file(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding()])
    client = FakeClient([valid_patch_json("src/other.py")])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert "unexpected file" in summary.suggestions[0].errors[0]
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_handles_ollama_failure(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding()])
    client = FakeClient([OllamaConnectionError("Ollama is not reachable")])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert summary.patches_failed == 1
    assert summary.suggestions[0].errors == ["Ollama is not reachable"]
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_handles_invalid_model_json(tmp_path):
    project, _source = make_project(tmp_path)
    report_path = write_audit_report(tmp_path / "audit.json", [finding()])
    client = FakeClient(["not json"])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert summary.patches_failed == 1
    assert summary.suggestions[0].status == "failed"
    assert not (tmp_path / "reports" / "patches").exists()


def test_patch_suggestion_schema_accepts_valid_example():
    valid = {
        "status": "suggested",
        "file_path": "src/main.py",
        "finding_type": "code_quality",
        "severity": "high",
        "summary": "Rename variable.",
        "diff": "--- a/src/main.py\n+++ b/src/main.py\n",
        "not_applied": True,
        "errors": [],
    }

    validate(valid, load_schema("patch_suggestion.schema.json"))


def test_patch_suggestion_schema_rejects_invalid_status():
    invalid = {
        "status": "applied",
        "file_path": "src/main.py",
        "finding_type": "code_quality",
        "severity": "high",
        "summary": "Rename variable.",
        "diff": "--- a/src/main.py\n+++ b/src/main.py\n",
        "not_applied": True,
        "errors": [],
    }

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("patch_suggestion.schema.json"))


def test_suggest_patch_cli_supports_report_alias_and_dry_run(monkeypatch, capsys, tmp_path):
    def fake_suggest_patches(*args, **kwargs):
        assert args[0] == tmp_path
        assert kwargs["report_path"] == tmp_path / "audit.json"
        assert kwargs["max_patches"] == 2
        assert kwargs["output_dir"] == tmp_path / "reports"
        assert kwargs["dry_run"] is True

        class FakeSummary:
            def to_dict(self):
                return {
                    "mode": "suggest_patch",
                    "status": "dry_run",
                    "patches_created": 0,
                    "warning": PATCH_WARNING,
                    "candidates": [{"file_path": "src/main.py"}],
                }

        return FakeSummary()

    monkeypatch.setattr("governor.main.suggest_patches", fake_suggest_patches)

    exit_code = main(
        [
            "suggest-patch",
            str(tmp_path),
            "--report",
            str(tmp_path / "audit.json"),
            "--max-patches",
            "2",
            "--output-dir",
            str(tmp_path / "reports"),
            "--dry-run",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "suggest_patch"
    assert output["status"] == "dry_run"
    assert output["warning"] == PATCH_WARNING
