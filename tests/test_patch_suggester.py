import json

from governor.main import main
from governor.ollama_client import OllamaConfig
from governor.patch_suggester import PATCH_WARNING, suggest_patches


class FakeClient:
    def __init__(self, responses):
        self.config = OllamaConfig(model="demo-model", max_chars_per_file=1000)
        self.responses = list(responses)
        self.calls = []

    def analyze_text_with_model(self, prompt, text):
        self.calls.append({"prompt": prompt, "text": text})
        return self.responses.pop(0)


def write_report(path, findings):
    report = {
        "status": "completed",
        "project_path": "/project",
        "summary": "Audit summary.",
        "findings_by_priority": {
            "critical": [],
            "high": findings,
            "medium": [],
            "low": [],
            "none": [],
        },
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


def test_suggest_patches_writes_reviewable_diff_without_modifying_project(tmp_path):
    project = tmp_path / "project"
    source = project / "src" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("x = 1\n", encoding="utf-8")
    report_path = write_report(tmp_path / "audit.json", [finding()])
    client = FakeClient(
        [
            """--- a/src/main.py
+++ b/src/main.py
@@ -1 +1 @@
-x = 1
+value = 1
"""
        ]
    )

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed"
    assert summary.mode == "suggest_patch"
    assert summary.patches_created == 1
    assert summary.warning == PATCH_WARNING
    assert source.read_text(encoding="utf-8") == "x = 1\n"
    patch_path = tmp_path / "reports" / "patches"
    written = list(patch_path.glob("*.diff"))
    assert len(written) == 1
    patch_text = written[0].read_text(encoding="utf-8")
    assert PATCH_WARNING in patch_text
    assert "--- a/src/main.py" in patch_text
    assert "+++ b/src/main.py" in patch_text
    assert "src/main.py" in client.calls[0]["prompt"]


def test_suggest_patches_requires_existing_findings(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    report_path = write_report(tmp_path / "audit.json", [])
    client = FakeClient([])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "no_findings"
    assert summary.patches_created == 0
    assert summary.findings_considered == 0
    assert client.calls == []
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_rejects_missing_finding_file(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    report_path = write_report(tmp_path / "audit.json", [finding("missing.py")])
    client = FakeClient([])

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert summary.patches_created == 0
    assert summary.patches_failed == 1
    assert "not found" in summary.proposals[0].errors[0].lower() or "no such file" in summary.proposals[0].errors[0].lower()
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patches_rejects_diff_for_another_file(tmp_path):
    project = tmp_path / "project"
    source = project / "src" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("x = 1\n", encoding="utf-8")
    report_path = write_report(tmp_path / "audit.json", [finding()])
    client = FakeClient(
        [
            """--- a/src/other.py
+++ b/src/other.py
@@ -1 +1 @@
-x = 1
+value = 1
"""
        ]
    )

    summary = suggest_patches(
        project,
        report_path=report_path,
        output_dir=tmp_path / "reports",
        client=client,
    )

    assert summary.status == "completed_with_errors"
    assert summary.patches_created == 0
    assert "unexpected file" in summary.proposals[0].errors[0]
    assert not (tmp_path / "reports" / "patches").exists()


def test_suggest_patch_cli_prints_json_summary(monkeypatch, capsys, tmp_path):
    def fake_suggest_patches(*args, **kwargs):
        assert args[0] == tmp_path
        assert kwargs["report_path"] == tmp_path / "audit.json"
        assert kwargs["max_findings"] == 2
        assert kwargs["output_dir"] == tmp_path / "reports"

        class FakeSummary:
            def to_dict(self):
                return {
                    "mode": "suggest_patch",
                    "status": "completed",
                    "patches_created": 1,
                    "warning": PATCH_WARNING,
                }

        return FakeSummary()

    monkeypatch.setattr("governor.main.suggest_patches", fake_suggest_patches)

    exit_code = main(
        [
            "suggest-patch",
            str(tmp_path),
            "--report-path",
            str(tmp_path / "audit.json"),
            "--max-findings",
            "2",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "suggest_patch"
    assert output["warning"] == PATCH_WARNING
