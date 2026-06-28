import json
import importlib
from pathlib import Path

from adapters.common.audit_request import AuditRequest
from adapters.common.audit_response import AuditResponse
from adapters.common.run_audit import run_audit
from governor.ollama_client import OllamaConfig


class FailingModelClient:
    def __init__(self):
        self.config = OllamaConfig(model="demo-model", max_chars_per_file=1000)

    def analyze_text_with_model(self, prompt, text):
        raise AssertionError("dry-run must not call Ollama")


def test_audit_request_accepts_common_contract():
    request = AuditRequest.from_dict(
        {
            "path": "D:/project",
            "profile": "windows_folder",
            "mode": "config_audit",
            "max_tasks": 3,
            "use_memory": True,
            "use_graphify": False,
            "read_only": True,
        }
    )

    assert request.profile == "windows_folder"
    assert request.core_profile == "general"
    assert request.mode == "config_audit"
    assert request.max_tasks == 3
    assert request.to_dict()["read_only"] is True


def test_run_audit_rejects_read_only_false(tmp_path):
    response = run_audit(
        {
            "path": str(tmp_path),
            "read_only": False,
        },
        adapter="cli",
    )

    data = response.to_dict()
    assert data["status"] == "failed"
    assert data["adapter"] == "cli"
    assert data["errors"] == ["read_only=false rejected"]


def test_audit_request_rejects_excessive_max_tasks(tmp_path):
    response = run_audit({"path": str(tmp_path), "max_tasks": 101}, adapter="cli")

    data = response.to_dict()
    assert data["status"] == "failed"
    assert "less than or equal to 100" in data["summary"]


def test_run_audit_missing_path_returns_json_safe_error(tmp_path):
    missing = tmp_path / "missing"

    response = run_audit({"path": str(missing)}, adapter="cli")

    data = response.to_dict()
    assert data["status"] == "failed"
    assert data["project_path"] == str(missing)
    assert data["errors"]
    json.dumps(data)


def test_run_audit_dry_run_does_not_call_ollama_or_write_results(tmp_path):
    project = tmp_path / "project"
    output_dir = tmp_path / "reports"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")

    response = run_audit(
        {"path": str(project), "max_tasks": 1},
        adapter="cli",
        output_dir=output_dir,
        client=FailingModelClient(),
        dry_run=True,
    )

    data = response.to_dict()
    assert data["status"] == "completed"
    assert data["tasks_processed"] == 1
    assert data["report_markdown"] == ""
    assert data["report_json"] == ""
    assert (output_dir / "scan_result.json").exists()
    assert (output_dir / "tasks.json").exists()
    assert not (output_dir / "task_results.json").exists()


def test_audit_response_is_always_json_serializable():
    response = AuditResponse.failed(
        adapter="openclaw",
        project_path="D:/project",
        summary="Ollama is not reachable",
    )

    encoded = response.to_json()
    decoded = json.loads(encoded)
    assert decoded["status"] == "failed"
    assert decoded["adapter"] == "openclaw"
    assert decoded["errors"] == ["Ollama is not reachable"]


def test_opencode_adapter_exists_and_uses_common_contract(tmp_path, monkeypatch):
    opencode_module = importlib.import_module("adapters.opencode.local_scope_audit")

    def fake_run_audit(request, *, adapter, output_dir, client=None, memory=None):
        assert request.path == str(tmp_path)
        assert adapter == "opencode"
        return AuditResponse(
            status="completed",
            adapter="opencode",
            project_path=str(tmp_path),
            profile_detected="general",
            summary="ok",
        )

    monkeypatch.setattr(opencode_module, "run_audit", fake_run_audit)

    response = opencode_module.local_scope_audit(path=tmp_path)

    assert response["status"] == "completed"
    assert response["adapter"] == "opencode"
    assert response["summary"] == "ok"


def test_adapters_do_not_expose_write_or_command_tools():
    adapters_root = Path(__file__).parents[1] / "adapters"
    forbidden = {"read_file", "write_file", "run_command", "apply_patch"}

    exposed_names = {path.stem for path in adapters_root.rglob("*.py")}

    assert forbidden.isdisjoint(exposed_names)
