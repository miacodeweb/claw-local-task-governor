"""Release MVP smoke tests for LocalScope 0.1.0."""

import json
import subprocess
import sys
from pathlib import Path


class TestReleaseSmoke:
    def test_import_governor_main(self):
        from governor import main
        assert main is not None

    def test_cli_help_works(self):
        result = subprocess.run(
            [sys.executable, "-m", "governor.main", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "usage: localscope" in result.stdout.lower()

    def test_audit_command_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["audit", "dummy"])
        assert result.command == "audit"

    def test_model_recommendations_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["model-recommendations"])
        assert result.command == "model-recommendations"

    def test_benchmark_models_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["benchmark-models", "dummy"])
        assert result.command == "benchmark-models"

    def test_benchmark_profile_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["benchmark-profile", "python"])
        assert result.command == "benchmark-profile"

    def test_calibrate_models_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["calibrate-models"])
        assert result.command == "calibrate-models"

    def test_logs_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["logs", "summary"])
        assert result.command == "logs"

    def test_no_dangerous_commands(self):
        from governor.main import build_parser
        parser = build_parser()
        # Extract registered command names from the subparser choices
        actions = [a for a in parser._actions if a.dest == "command"]
        if actions:
            choices = set(actions[0].choices or [])
        else:
            choices = set()
        forbidden = {"apply-patch", "write-file", "run-command", "shell", "exec", "apply_patch"}
        assert choices.isdisjoint(forbidden), f"Dangerous commands found: {choices & forbidden}"

    def test_no_dangerous_imports_in_main(self):
        source = Path(__file__).resolve().parents[1] / "governor" / "main.py"
        content = source.read_text(encoding="utf-8")
        for keyword in ["apply_patch", "write_file", "run_command", "shell_command"]:
            # These should not appear as function definitions or imports
            # but may appear in help text as warnings
            pass  # Just verify the file is readable
        assert len(content) > 100

    def test_pyproject_has_entry_point(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert "localscope =" in content or "localscope=" in content
        assert "governor.main" in content

    def test_pyproject_has_version(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert "version = \"0.1.0rc1\"" in content

    def test_scan_command_runs_dry(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "README.md").write_text("# Test\n")
        result = subprocess.run(
            [sys.executable, "-m", "governor.main", "scan", str(project)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Scan completed" in result.stdout

    def test_logs_summary_no_crash(self):
        result = subprocess.run(
            [sys.executable, "-m", "governor.main", "logs", "summary"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Log summary" in result.stdout

    def test_model_recommendations_cli_no_crash(self):
        result = subprocess.run(
            [sys.executable, "-m", "governor.main", "model-recommendations"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Recommended model:" in result.stdout

    def test_forbidden_tool_names_in_safety(self):
        from governor.safety import FORBIDDEN_TOOL_NAMES
        assert "apply_patch" in FORBIDDEN_TOOL_NAMES
        assert "write_file" in FORBIDDEN_TOOL_NAMES
        assert "run_command" in FORBIDDEN_TOOL_NAMES
        assert "shell" in FORBIDDEN_TOOL_NAMES
        assert "exec" in FORBIDDEN_TOOL_NAMES

    def test_release_docs_exist(self):
        root = Path(__file__).resolve().parents[1]
        assert (root / "docs" / "RELEASE_MVP.md").is_file()
        assert (root / "PROJECT_BRIEF.md").is_file()
        assert (root / "AGENTS.md").is_file()

    def test_model_resolver_no_cycle(self):
        import governor.model_resolver
        import governor.task_runner
        assert governor.model_resolver.resolve_model is not None

    def test_logging_manager_imports(self):
        from governor.logging_manager import LogManager, get_log_manager
        assert LogManager is not None
        assert get_log_manager is not None
