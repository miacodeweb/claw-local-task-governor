import importlib
import json
from pathlib import Path

from governor.ollama_client import OllamaConnectionError


def test_opencode_cli_stdout_is_valid_json(monkeypatch, capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.opencode.local_scope_audit")

    def fake_local_scope_audit(**kwargs):
        assert kwargs["path"] == tmp_path
        assert kwargs["profile"] == "auto"
        assert kwargs["mode"] == "general"
        assert kwargs["max_tasks"] == 5
        return {
            "status": "completed",
            "adapter": "opencode",
            "project_path": str(tmp_path),
            "profile_detected": "general",
            "report_markdown": "reports/audit.md",
            "report_json": "reports/audit.json",
            "tasks_processed": 5,
            "reused": 0,
            "json_valid": 5,
            "json_repaired": 0,
            "json_failed": 0,
            "summary": "ok",
            "errors": [],
        }

    monkeypatch.setattr(adapter_module, "local_scope_audit", fake_local_scope_audit)

    exit_code = adapter_module.main(["--path", str(tmp_path)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert output["status"] == "completed"
    assert output["adapter"] == "opencode"


def test_opencode_cli_rejects_read_only_false(capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.opencode.local_scope_audit")

    exit_code = adapter_module.main(["--path", str(tmp_path), "--read-only", "false"])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["adapter"] == "opencode"
    assert output["errors"] == ["read_only=false rejected"]


def test_opencode_cli_missing_path_returns_json_error(capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.opencode.local_scope_audit")
    missing = tmp_path / "missing"

    exit_code = adapter_module.main(["--path", str(missing)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["adapter"] == "opencode"
    assert output["project_path"] == str(missing)
    assert output["errors"]


def test_opencode_cli_internal_errors_are_json(monkeypatch, capsys, tmp_path):
    adapter_module = importlib.import_module("adapters.opencode.local_scope_audit")

    def fake_local_scope_audit(**kwargs):
        raise OllamaConnectionError("Ollama is not reachable")

    monkeypatch.setattr(adapter_module, "local_scope_audit", fake_local_scope_audit)

    exit_code = adapter_module.main(["--path", str(tmp_path)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert output["status"] == "failed"
    assert output["adapter"] == "opencode"
    assert output["errors"] == ["Ollama is not reachable"]


def test_opencode_local_project_alias_uses_opencode_adapter(monkeypatch, tmp_path):
    alias_module = importlib.import_module("adapters.opencode.local_project_audit")

    def fake_local_scope_audit(**kwargs):
        assert kwargs["path"] == tmp_path
        return {
            "status": "completed",
            "adapter": "opencode",
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

    monkeypatch.setattr(alias_module, "local_scope_audit", fake_local_scope_audit)

    response = alias_module.local_project_audit(path=tmp_path)

    assert response["status"] == "completed"
    assert response["adapter"] == "opencode"


def test_opencode_adapter_does_not_expose_write_or_command_tools():
    adapter_root = Path(__file__).parents[1] / "adapters" / "opencode"
    forbidden = {"read_file", "write_file", "run_command", "apply_patch"}
    exposed_names = {path.stem for path in adapter_root.rglob("*.py")}
    adapter_text = "\n".join(path.read_text(encoding="utf-8") for path in adapter_root.rglob("*.py"))

    assert forbidden.isdisjoint(exposed_names)
    assert "write_file" not in adapter_text
    assert "run_command" not in adapter_text
    assert "apply_patch" not in adapter_text
