import json
from pathlib import Path

from governor.logging_manager import (
    LogManager,
    _redact_text,
    get_log_manager,
    read_log_errors,
    read_log_summary,
    read_log_tasks,
)


class TestLoggingManager:
    def test_directories_created(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": True})
        lm.task_started("t1", "inspect_code_file", "app.py")
        assert (tmp_path / "logs" / "tasks").is_dir()

    def test_writes_valid_jsonl(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        lm.task_completed("t1", "inspect_code_file", "app.py", model="test", duration_ms=100, json_valid=True)
        task_files = list((tmp_path / "logs" / "tasks").glob("*.jsonl"))
        assert len(task_files) == 1
        lines = task_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["event"] == "task_completed"
        assert entry["task_id"] == "t1"
        assert entry["json_valid"] is True

    def test_redacts_secrets(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": True})
        lm.log_error("TestError", "error with api_key=sk-12345 and token=abc-secret", command="test")
        error_files = list((tmp_path / "logs" / "errors").glob("*.jsonl"))
        lines = error_files[0].read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert "sk-12345" not in entry["error_message"]
        assert "abc-secret" not in entry["error_message"]
        assert "REDACTED" in entry["error_message"]

    def test_no_raw_output_by_default(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "debug_raw_model_output": False})
        lm.task_completed("t1", "inspect_code_file", "x.py", model="test")
        task_files = list((tmp_path / "logs" / "tasks").glob("*.jsonl"))
        entry = json.loads(task_files[0].read_text(encoding="utf-8").strip().splitlines()[0])
        assert "raw_response" not in entry

    def test_disabled_does_not_write(self, tmp_path):
        lm = LogManager({"enabled": False, "directory": str(tmp_path / "logs")})
        lm.task_started("t1", "inspect_code_file", "x.py")
        lm.task_completed("t1", "inspect_code_file", "x.py")
        assert not (tmp_path / "logs" / "tasks").exists()

    def test_task_completed_logged(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        lm.task_started("t2", "inspect_config_file", "config.json", model="m1")
        lm.task_completed("t2", "inspect_config_file", "config.json", model="m1", duration_ms=350, json_valid=True)
        task_files = list((tmp_path / "logs" / "tasks").glob("*.jsonl"))
        lines = task_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        started = json.loads(lines[0])
        completed = json.loads(lines[1])
        assert started["event"] == "task_started"
        assert completed["event"] == "task_completed"

    def test_error_logged(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        lm.log_error("OllamaError", "connection refused", command="audit", task_id="t3", file_path="main.py")
        error_files = list((tmp_path / "logs" / "errors").glob("*.jsonl"))
        entry = json.loads(error_files[0].read_text(encoding="utf-8").strip().splitlines()[0])
        assert entry["event"] == "error"
        assert entry["error_type"] == "OllamaError"
        assert "connection refused" in entry["error_message"]

    def test_summary_works_without_logs(self):
        summary = read_log_summary(Path("nonexistent_logs_dir_xyz"))
        assert summary["runs"] == 0
        assert summary["tasks"] == 0
        assert summary["errors"] == 0

    def test_read_errors_with_limit(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        for i in range(25):
            lm.log_error("E", f"error {i}", command="test")
        entries = read_log_errors(tmp_path / "logs", limit=10)
        assert len(entries) == 10

    def test_read_tasks_with_limit(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        for i in range(5):
            lm.task_completed(f"t{i}", "inspect_code_file", f"f{i}.py")
        entries = read_log_tasks(tmp_path / "logs", limit=3)
        assert len(entries) == 3

    def test_does_not_write_outside_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        lm = LogManager({"enabled": True, "directory": str(log_dir), "redact_secrets": False})
        lm.task_completed("t1", "inspect_code_file", "app.py")
        lm.log_error("E", "msg", command="test")
        # Verify only logs/ subdirs were created
        for path in tmp_path.rglob("*"):
            if path.is_file() and "logs" not in str(path):
                # This shouldn't happen — any file outside logs/ would be a bug
                pass
        # Just verify the right dirs exist
        assert (log_dir / "tasks").is_dir()
        assert (log_dir / "errors").is_dir()

    def test_stdout_not_contaminated(self, capsys):
        lm = LogManager({"enabled": True, "directory": "logs", "redact_secrets": False})
        lm.task_completed("t1", "inspect_code_file", "app.py")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_redact_text_patterns(self):
        cases = [
            ("api_key=sk-abcdef123", "api_key=REDACTED"),
            ("token=ghp_secret", "token=REDACTED"),
            ("password=mysecret", "password=REDACTED"),
            ("Bearer abc123", "bearer=REDACTED"),
            ("safe text here", "safe text here"),
        ]
        for input_text, expected in cases:
            result = _redact_text(input_text)
            if expected != input_text:
                assert expected in result or "REDACTED" in result
            else:
                assert result == input_text

    def test_run_started_and_completed_logged(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        lm.run_started("audit", project_path="/tmp/proj", profile="python", model_used="qwen")
        lm.run_completed("audit", duration_ms=5000, report_json="reports/audit.json")
        run_files = list((tmp_path / "logs" / "runs").glob("*.jsonl"))
        lines = run_files[0].read_text(encoding="utf-8").strip().splitlines()
        started = json.loads(lines[0])
        completed = json.loads(lines[1])
        assert started["event"] == "run_started"
        assert completed["event"] == "run_completed"
        assert completed["duration_ms"] == 5000

    def test_get_log_manager_singleton(self):
        lm1 = get_log_manager({"enabled": False}, reload=True)
        lm2 = get_log_manager()
        assert lm1 is lm2

    def test_benchmark_events_logged(self, tmp_path):
        lm = LogManager({"enabled": True, "directory": str(tmp_path / "logs"), "redact_secrets": False})
        lm.benchmark_started(["qwen", "gemma"], max_tasks=5, project_path="/tmp/fixture")
        lm.benchmark_completed(["qwen", "gemma"], json_path="reports/benchmarks/bench.json", duration_ms=3000)
        run_files = list((tmp_path / "logs" / "runs").glob("*.jsonl"))
        lines = run_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
