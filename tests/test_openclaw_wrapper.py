import json
import importlib

from governor.ollama_client import OllamaConnectionError
from openclaw import local_project_audit as wrapper


def test_wrapper_returns_valid_json(monkeypatch, capsys, tmp_path):
    def fake_local_project_audit(**kwargs):
        assert kwargs["path"] == tmp_path
        assert kwargs["profile"] == "auto"
        assert kwargs["max_tasks"] == 5
        return {
            "status": "completed",
            "adapter": "openclaw",
            "project_path": str(tmp_path),
            "profile_detected": "general",
            "report_markdown": "reports/audit.md",
            "report_json": "reports/audit.json",
            "tasks_processed": 1,
            "reused": 0,
            "json_valid": 1,
            "json_repaired": 0,
            "json_failed": 0,
            "summary": "ok",
            "errors": [],
        }

    monkeypatch.setattr(wrapper, "local_project_audit", fake_local_project_audit)

    exit_code = wrapper.main(["--path", str(tmp_path), "--max-tasks", "5", "--profile", "auto"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["adapter"] == "openclaw"
    assert output["errors"] == []
    assert capsys.readouterr().err == ""


def test_wrapper_rejects_read_only_false_with_json(capsys, tmp_path):
    exit_code = wrapper.main(["--path", str(tmp_path), "--read-only", "false"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["errors"] == ["read_only=false rejected"]


def test_wrapper_handles_missing_path_with_json(capsys, tmp_path):
    missing = tmp_path / "missing"

    exit_code = wrapper.main(["--path", str(missing)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["project_path"] == str(missing)
    assert output["errors"]


def test_wrapper_handles_ollama_error_without_breaking_json(monkeypatch, capsys, tmp_path):
    def fake_local_project_audit(**kwargs):
        raise OllamaConnectionError("Ollama is not reachable")

    monkeypatch.setattr(wrapper, "local_project_audit", fake_local_project_audit)

    exit_code = wrapper.main(["--path", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["errors"] == ["Ollama is not reachable"]


def test_local_scope_audit_cli_stdout_is_json_only(monkeypatch, capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.openclaw.local_scope_audit")

    def fake_local_scope_audit(**kwargs):
        assert kwargs["path"] == tmp_path
        assert kwargs["profile"] == "auto"
        assert kwargs["max_tasks"] == 2
        return {
            "status": "completed",
            "adapter": "openclaw",
            "project_path": str(tmp_path),
            "profile_detected": "general",
            "report_markdown": "reports/audit.md",
            "report_json": "reports/audit.json",
            "tasks_processed": 2,
            "reused": 0,
            "json_valid": 2,
            "json_repaired": 0,
            "json_failed": 0,
            "summary": "ok",
            "errors": [],
        }

    monkeypatch.setattr(adapter_module, "local_scope_audit", fake_local_scope_audit)

    exit_code = adapter_module.main(["--path", str(tmp_path), "--max-tasks", "2"])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert output["status"] == "completed"
    assert output["adapter"] == "openclaw"


def test_local_scope_audit_cli_errors_are_json(monkeypatch, capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.openclaw.local_scope_audit")

    def fake_local_scope_audit(**kwargs):
        raise OllamaConnectionError("Ollama is not reachable")

    monkeypatch.setattr(adapter_module, "local_scope_audit", fake_local_scope_audit)

    exit_code = adapter_module.main(["--path", str(tmp_path)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["adapter"] == "openclaw"
    assert output["errors"] == ["Ollama is not reachable"]


def test_local_scope_audit_cli_rejects_read_only_false(capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.openclaw.local_scope_audit")

    exit_code = adapter_module.main(["--path", str(tmp_path), "--read-only", "false"])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["errors"] == ["read_only=false rejected"]


def test_local_scope_audit_parser_exposes_expected_safe_arguments():
    adapter_module = importlib.import_module("adapters.openclaw.local_scope_audit")
    parser = adapter_module.build_parser()

    parsed = parser.parse_args(
        [
            "--path",
            "D:/project",
            "--profile",
            "auto",
            "--mode",
            "general",
            "--max-tasks",
            "5",
            "--use-memory",
            "true",
            "--use-graphify",
            "true",
            "--read-only",
            "true",
        ]
    )

    assert parsed.path == "D:/project"
    assert parsed.profile == "auto"
    assert parsed.mode == "general"
    assert parsed.max_tasks == 5
    assert parsed.use_memory == "true"
    assert parsed.use_graphify == "true"
    assert parsed.read_only == "true"


def test_local_scope_audit_cli_missing_path_returns_json(capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.openclaw.local_scope_audit")
    missing = tmp_path / "missing"

    exit_code = adapter_module.main(["--path", str(missing)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["project_path"] == str(missing)
    assert output["errors"]


def test_legacy_shim_calls_local_scope_adapter(monkeypatch, capsys, tmp_path):
    called = {}

    def fake_local_project_audit(**kwargs):
        called["path"] = kwargs["path"]
        return {
            "status": "completed",
            "adapter": "openclaw",
            "project_path": str(tmp_path),
            "profile_detected": "general",
            "report_markdown": "",
            "report_json": "",
            "tasks_processed": 0,
            "reused": 0,
            "json_valid": 0,
            "json_repaired": 0,
            "json_failed": 0,
            "summary": "ok",
            "errors": [],
        }

    monkeypatch.setattr(wrapper, "local_project_audit", fake_local_project_audit)

    exit_code = wrapper.main(["--path", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert called["path"] == tmp_path
    assert output["adapter"] == "openclaw"
