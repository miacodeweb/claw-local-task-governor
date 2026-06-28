import json

from adapters.common.audit_response import AuditResponse
from governor import main as governor_main
from governor.ollama_client import OllamaConfig, OllamaConnectionError


class FakeOllamaClient:
    def __init__(self, config):
        self.config = config

    def check_ollama_available(self):
        return True

    def list_models(self):
        return ["demo:latest"]

    def analyze_text_with_model(self, prompt, text):
        return "Ollama connection works."


def test_ollama_test_command_checks_connection_and_prints_response(monkeypatch, capsys):
    config = OllamaConfig(base_url="http://127.0.0.1:11434", model="demo:latest")
    monkeypatch.setattr(governor_main, "load_ollama_config", lambda: config)
    monkeypatch.setattr(governor_main, "OllamaClient", FakeOllamaClient)

    exit_code = governor_main.main(["ollama-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Ollama test completed." in output
    assert "Configured model: demo:latest" in output
    assert "- demo:latest (configured)" in output
    assert "Ollama connection works." in output


def test_audit_command_dry_run_prints_human_and_structured_output(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_run_audit(request, *, adapter, output_dir, dry_run):
        captured["request"] = request
        captured["adapter"] = adapter
        captured["output_dir"] = output_dir
        captured["dry_run"] = dry_run
        return AuditResponse(
            status="completed",
            adapter="cli",
            project_path=str(tmp_path),
            profile_detected="python",
            tasks_processed=2,
            summary="Audit dry-run completed.",
        )

    monkeypatch.setattr(governor_main, "run_audit", fake_run_audit)

    exit_code = governor_main.main(
        [
            "audit",
            str(tmp_path),
            "--profile",
            "python",
            "--max-tasks",
            "2",
            "--dry-run",
            "--no-memory",
            "--no-graphify",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["adapter"] == "cli"
    assert captured["dry_run"] is True
    assert captured["request"]["profile"] == "python"
    assert captured["request"]["max_tasks"] == 2
    assert captured["request"]["use_memory"] is False
    assert captured["request"]["use_graphify"] is False
    assert "Audit dry-run completed." in output
    assert "Model calls: skipped" in output
    assert '"adapter": "cli"' in output


def test_audit_command_path_missing_returns_error(capsys, tmp_path):
    missing = tmp_path / "missing"

    exit_code = governor_main.main(["audit", str(missing)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Audit failed." in output
    assert "Errors:" in output
    assert str(missing) in output


def test_audit_command_rejects_read_only_false(capsys, tmp_path):
    output_dir = tmp_path / "reports"

    exit_code = governor_main.main(
        [
            "audit",
            str(tmp_path),
            "--read-only",
            "false",
            "--output-dir",
            str(output_dir),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Audit failed." in output
    assert "read_only=false rejected" in output
    assert not output_dir.exists()


def test_audit_command_passes_max_tasks(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_run_audit(request, *, adapter, output_dir, dry_run):
        captured["max_tasks"] = request["max_tasks"]
        return AuditResponse(
            status="completed",
            adapter="cli",
            project_path=str(tmp_path),
            profile_detected="general",
            tasks_processed=7,
            summary="ok",
        )

    monkeypatch.setattr(governor_main, "run_audit", fake_run_audit)

    exit_code = governor_main.main(["audit", str(tmp_path), "--max-tasks", "7"])

    assert exit_code == 0
    assert captured["max_tasks"] == 7
    assert "Structured response:" in capsys.readouterr().out


def test_audit_command_outputs_structured_json(monkeypatch, capsys, tmp_path):
    def fake_run_audit(request, *, adapter, output_dir, dry_run):
        return AuditResponse(
            status="completed",
            adapter="cli",
            project_path=str(tmp_path),
            profile_detected="general",
            report_markdown="reports/audit.md",
            report_json="reports/audit.json",
            tasks_processed=1,
            json_valid=1,
            summary="ok",
        )

    monkeypatch.setattr(governor_main, "run_audit", fake_run_audit)

    exit_code = governor_main.main(["audit", str(tmp_path)])
    output = capsys.readouterr().out
    structured = json.loads(output.split("Structured response:\n", 1)[1])

    assert exit_code == 0
    assert structured["status"] == "completed"
    assert structured["adapter"] == "cli"
    assert structured["report_json"] == "reports/audit.json"


def test_ollama_test_command_reports_connection_error(monkeypatch, capsys):
    class FailingClient(FakeOllamaClient):
        def check_ollama_available(self):
            raise OllamaConnectionError("Ollama is not reachable")

    monkeypatch.setattr(governor_main, "load_ollama_config", lambda: OllamaConfig())
    monkeypatch.setattr(governor_main, "OllamaClient", FailingClient)

    exit_code = governor_main.main(["ollama-test"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Ollama test failed: Ollama is not reachable" in output


def test_graphify_info_command_prints_diagnostics(monkeypatch, capsys, tmp_path):
    def fake_get_graph_summary(path):
        assert path == tmp_path
        return {
            "available": True,
            "graph_json": str(tmp_path / "graphify-out" / "graph.json"),
            "graph_report": None,
            "graph_html": None,
            "nodes_detected": 2,
            "edges_detected": 1,
            "referenced_files": ["src/main.py"],
            "warnings": ["format partially recognized"],
        }

    monkeypatch.setattr(governor_main, "get_graph_summary", fake_get_graph_summary)

    exit_code = governor_main.main(["graphify-info", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Graphify detectado: si" in output
    assert "Nodos detectados: 2" in output
    assert "- src/main.py" in output
    assert "format partially recognized" in output


def test_scan_command_passes_forced_profile(monkeypatch, capsys, tmp_path):
    class FakeScanResult:
        files_found = 2
        files_ignored = 0
        relevant_files = 2
        profile_detected = "wordpress"

    captured = {}

    def fake_scan_project(path, *, output_dir, profile):
        captured["path"] = path
        captured["output_dir"] = output_dir
        captured["profile"] = profile
        return FakeScanResult()

    monkeypatch.setattr(governor_main, "scan_project", fake_scan_project)

    exit_code = governor_main.main(["scan", str(tmp_path), "--profile", "wordpress"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["path"] == tmp_path
    assert captured["profile"] == "wordpress"
    assert "Detected profile: wordpress" in output


def test_tasks_command_prints_priority_and_graphify_summary(monkeypatch, capsys, tmp_path):
    class FakeQueue:
        tasks_total = 3
        tasks_pending = 3
        tasks_with_graphify_signal = 1
        tasks_by_priority = {"high": 1, "medium": 1, "low": 1}
        profile = "general"

    captured = {}

    def fake_scan_project(path, *, output_dir, profile):
        captured["scan_path"] = path
        captured["scan_output_dir"] = output_dir
        captured["profile"] = profile

    def fake_generate_tasks_from_scan_result(scan_result_path, *, output_dir):
        captured["scan_result_path"] = scan_result_path
        captured["tasks_output_dir"] = output_dir
        return FakeQueue()

    monkeypatch.setattr(governor_main, "scan_project", fake_scan_project)
    monkeypatch.setattr(governor_main, "generate_tasks_from_scan_result", fake_generate_tasks_from_scan_result)

    exit_code = governor_main.main(
        ["tasks", str(tmp_path), "--profile", "python", "--output-dir", str(tmp_path / "reports")]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["scan_path"] == tmp_path
    assert captured["profile"] == "python"
    assert "Tasks created: 3" in output
    assert "Tasks with Graphify signal: 1" in output
    assert "- high: 1" in output
    assert "- medium: 1" in output
    assert "- low: 1" in output


def test_run_tasks_cli_supports_dry_run(monkeypatch, capsys, tmp_path):
    class FakeSummary:
        dry_run = True
        tasks_requested = 5
        tasks_selected = 1
        dry_run_tasks = [
            type(
                "DryRunItem",
                (),
                {
                    "task_id": "task-0001",
                    "task_type": "inspect_code_file",
                    "file_path": "main.py",
                    "valid_path": True,
                    "truncated": False,
                    "prompt_preview": "Analyze one file",
                    "errors": [],
                },
            )()
        ]

    captured = {}

    def fake_run_pending_tasks(
        path,
        *,
        max_tasks,
        output_dir,
        dry_run,
        no_memory,
        profile_override,
        no_adaptive_limits,
        prompt_version,
        model_override=None,
        use_benchmark_recommendations=False,
    ):
        captured["path"] = path
        captured["max_tasks"] = max_tasks
        captured["output_dir"] = output_dir
        captured["dry_run"] = dry_run
        captured["no_memory"] = no_memory
        captured["profile_override"] = profile_override
        captured["no_adaptive_limits"] = no_adaptive_limits
        captured["prompt_version"] = prompt_version
        return FakeSummary()

    monkeypatch.setattr(governor_main, "run_pending_tasks", fake_run_pending_tasks)

    exit_code = governor_main.main(
        ["run-tasks", str(tmp_path), "--max-tasks", "5", "--dry-run", "--no-memory"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["path"] == tmp_path
    assert captured["max_tasks"] == 5
    assert captured["dry_run"] is True
    assert captured["no_memory"] is True
    assert captured["profile_override"] == "auto"
    assert captured["no_adaptive_limits"] is False
    assert captured["prompt_version"] is None
    assert "Task dry-run completed." in output
    assert "Output: not written in dry-run mode" in output


def test_report_cli_accepts_custom_results_path(monkeypatch, capsys, tmp_path):
    results_path = tmp_path / "task_results.json"
    output_dir = tmp_path / "reports"
    captured = {}

    def fake_load_audit_inputs(path, *, output_dir, results_path):
        captured["path"] = path
        captured["output_dir"] = output_dir
        captured["results_path"] = results_path
        return {"inputs": True}

    def fake_build_final_report(inputs):
        assert inputs == {"inputs": True}
        return {"summary": "ok", "report_paths": {"markdown": "", "json": ""}}

    def fake_write_audit_reports(report, *, output_dir):
        return output_dir / "audit.md", output_dir / "audit.json"

    monkeypatch.setattr(governor_main, "load_audit_inputs", fake_load_audit_inputs)
    monkeypatch.setattr(governor_main, "build_final_report", fake_build_final_report)
    monkeypatch.setattr(governor_main, "write_audit_reports", fake_write_audit_reports)

    exit_code = governor_main.main(
        [
            "report",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--results",
            str(results_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["path"] == tmp_path
    assert captured["output_dir"] == output_dir
    assert captured["results_path"] == results_path
    assert "Report generated." in output


def test_report_cli_prints_clear_error_for_missing_results(monkeypatch, capsys, tmp_path):
    def fake_load_audit_inputs(*args, **kwargs):
        raise FileNotFoundError("task results file not found: reports/task_results.json")

    monkeypatch.setattr(governor_main, "load_audit_inputs", fake_load_audit_inputs)

    exit_code = governor_main.main(["report", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Report failed: task results file not found" in output


def test_calibrate_models_accepts_config_files_dry_run(monkeypatch, capsys):
    captured = {}

    def fake_resolve_benchmark_models(args):
        return ["qwen2.5-coder:7b", "qwen3:8b"]

    def fake_run_profile_benchmark(**kwargs):
        captured.update(kwargs)
        return governor_main.BenchmarkDryRun(
            models=kwargs["models"],
            tasks=[{"profile": "config_files", "fixture": "tests/fixtures/calibration_projects/config_files_project"}],
            prompt_versions=["v1"],
            project_path="calibration_projects",
            max_tasks=kwargs["max_tasks"],
            output_dir=str(kwargs["output_dir"]),
            timeout_seconds=kwargs["timeout_seconds"],
            delay_between_models=kwargs["delay_between_models"],
            estimated_timeout_seconds=len(kwargs["models"]) * len(kwargs["profiles"]) * kwargs["max_tasks"] * kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(governor_main, "_resolve_benchmark_models", fake_resolve_benchmark_models)
    monkeypatch.setattr(governor_main, "run_profile_benchmark", fake_run_profile_benchmark)

    exit_code = governor_main.main(
        [
            "calibrate-models",
            "--profiles",
            "python",
            "javascript",
            "config_files",
            "--models",
            "qwen2.5-coder:7b",
            "qwen3:8b",
            "--max-tasks",
            "3",
            "--timeout-seconds",
            "300",
            "--dry-run",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["profiles"] == ["python", "javascript", "config_files"]
    assert captured["models"] == ["qwen2.5-coder:7b", "qwen3:8b"]
    assert captured["max_tasks"] == 3
    assert captured["timeout_seconds"] == 300
    assert captured["dry_run"] is True
    assert "Timeout per request: 300s" in output
    assert "Ollama calls: skipped (dry-run)" in output


def test_calibrate_models_rejects_invalid_timeout():
    try:
        governor_main.main(
            [
                "calibrate-models",
                "--profiles",
                "config_files",
                "--models",
                "qwen",
                "--timeout-seconds",
                "0",
                "--dry-run",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("invalid timeout should exit with argparse error")
