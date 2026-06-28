import json
from dataclasses import replace
from pathlib import Path

import pytest

from governor import main as governor_main
from governor.model_benchmark import BenchmarkDryRun
from governor.ollama_client import OllamaConfig
from governor.memory import SQLiteMemory
from governor.profile_benchmark import (
    ProfileBenchmarkReport,
    _build_global_summary,
    _resolve_profiles,
    run_profile_benchmark,
)


class FakeClient:
    def __init__(self, responses, model="test-model", max_chars_per_file=12000):
        self.responses = list(responses)
        self.config = replace(OllamaConfig(max_chars_per_file=max_chars_per_file), model=model)
        self.calls = []

    def analyze_text_with_model(self, prompt, text, max_chars=None):
        self.calls.append({"prompt": prompt, "text": text})
        if not self.responses:
            return '{"unknown": true}'
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def check_ollama_available(self):
        return True

    def list_models(self):
        return [self.config.model]


def valid_json(file_path="test.py"):
    return json.dumps({
        "file": file_path,
        "status": "ok",
        "risk": "none",
        "summary": "ok",
        "findings": [],
        "needs_related_file": False,
        "related_files": [],
    })


class TestProfileBenchmark:
    def test_resolve_all_profiles(self):
        profiles = _resolve_profiles(["all"])
        assert "python" in profiles
        assert "javascript" in profiles
        assert len(profiles) >= 5

    def test_resolve_single_profile(self):
        profiles = _resolve_profiles(["python"])
        assert profiles == ["python"]

    def test_config_files_is_valid_profile(self):
        profiles = _resolve_profiles(["config_files"])
        assert profiles == ["config_files"]

    def test_windows_and_linux_folder_profiles_are_valid(self):
        profiles = _resolve_profiles(["windows_folder", "linux_folder", "documentation"])
        assert profiles == ["windows_folder", "linux_folder", "documentation"]

    def test_resolve_invalid_skipped(self):
        profiles = _resolve_profiles(["python", "invalid", "javascript"])
        assert "python" in profiles
        assert "javascript" in profiles
        assert "invalid" not in profiles

    def test_mapping_covers_all_calibration_dirs(self):
        from governor.profile_benchmark import FIXTURE_DIR, PROFILE_FIXTURES
        for name, dir_name in PROFILE_FIXTURES.items():
            path = FIXTURE_DIR / dir_name
            assert path.is_dir(), f"{name} -> {dir_name} not found"

    def test_benchmark_profile_python_uses_correct_fixture(self, tmp_path):
        client = FakeClient(
            [valid_json("app.py"), valid_json("requirements.txt"), valid_json("README.md")],
            model="test-model",
        )
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        report = run_profile_benchmark(
            profiles=["python"],
            models=["test-model"],
            max_tasks=3,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        assert isinstance(report, ProfileBenchmarkReport)
        assert "python" in report.profiles
        py_data = report.profiles["python"]
        assert len(py_data["models"]) == 1
        m = py_data["models"][0]
        assert m["json_valid_rate"] >= 0.6

    def test_benchmark_profile_all_runs_multiple(self, tmp_path):
        resp = [valid_json("f.py")] * 99
        client = FakeClient(resp, model="all-model")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        report = run_profile_benchmark(
            profiles=["python", "javascript", "java"],
            models=["all-model"],
            max_tasks=1,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        assert isinstance(report, ProfileBenchmarkReport)
        assert len(report.profiles) >= 3

    def test_dry_run_does_not_call_ollama(self):
        client = FakeClient([valid_json("x.py")], model="nope")
        result = run_profile_benchmark(
            profiles=["python"],
            models=["nope"],
            max_tasks=2,
            client=client,
            dry_run=True,
        )
        assert len(client.calls) == 0
        assert isinstance(result, BenchmarkDryRun)

    def test_config_files_dry_run_does_not_call_ollama(self):
        client = FakeClient([valid_json("settings.json")], model="nope")
        result = run_profile_benchmark(
            profiles=["config_files"],
            models=["nope"],
            max_tasks=3,
            timeout_seconds=300,
            client=client,
            dry_run=True,
        )
        assert len(client.calls) == 0
        assert isinstance(result, BenchmarkDryRun)
        assert result.tasks[0]["profile"] == "config_files"
        assert "config_files_project" in str(result.tasks[0]["fixture"])
        assert result.timeout_seconds == 300

    def test_unknown_profile_is_rejected(self):
        result = run_profile_benchmark(
            profiles=["not_a_profile"],
            models=["demo"],
            dry_run=True,
        )
        assert isinstance(result, ProfileBenchmarkReport)
        assert result.errors == ["no valid profiles selected"]

    def test_output_json_is_valid(self, tmp_path):
        client = FakeClient([valid_json("app.py"), valid_json("x.py"), valid_json("y.py")], model="json-model")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        report = run_profile_benchmark(
            profiles=["python"],
            models=["json-model"],
            max_tasks=3,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        assert isinstance(report, ProfileBenchmarkReport)
        data = {
            "metadata": report.metadata,
            "profiles": report.profiles,
            "global_summary": report.global_summary,
            "errors": report.errors,
        }
        assert json.dumps(data)
        assert "profiles" in data

    def test_output_markdown_created(self, tmp_path):
        client = FakeClient([valid_json("app.py"), valid_json("x.py"), valid_json("y.py")], model="md-model")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        out = tmp_path / "benchmarks"
        run_profile_benchmark(
            profiles=["python"],
            models=["md-model"],
            max_tasks=3,
            client=client,
            memory=mem,
            output_dir=out,
        )
        md_files = list(out.glob("profile-benchmark-*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "# LocalScope Profile Model Benchmark" in content
        assert "python" in content

    def test_best_model_per_profile_computed(self, tmp_path):
        client = FakeClient([valid_json("a"), valid_json("a"), valid_json("a")], model="m1")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        report = run_profile_benchmark(
            profiles=["python", "javascript"],
            models=["m1"],
            max_tasks=3,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        for profile_name in ["python", "javascript"]:
            data = report.profiles.get(profile_name, {})
            assert data.get("best_overall_model") == "m1"

    def test_global_summary_computed(self):
        pr = {
            "py": {
                "best_overall_model": "a",
                "models": [
                    {"model": "a", "overall_score": 0.9},
                    {"model": "b", "overall_score": 0.5},
                ],
            },
            "js": {
                "best_overall_model": "a",
                "models": [
                    {"model": "a", "overall_score": 0.8},
                    {"model": "b", "overall_score": 0.7},
                ],
            },
            "java": {
                "best_overall_model": "b",
                "models": [
                    {"model": "b", "overall_score": 0.9},
                    {"model": "a", "overall_score": 0.6},
                ],
            },
        }
        gs = _build_global_summary(pr)
        assert gs["best_general_model"] == "a"

    def test_all_ollama_uses_listed_models(self):
        original_list = governor_main.ollama_list_models
        governor_main.ollama_list_models = lambda: ["m1", "m2", "m3"]
        try:
            import argparse
            ns = argparse.Namespace(all_ollama=True, models=None)
            result = governor_main._resolve_benchmark_models(ns)
            assert result == ["m1", "m2", "m3"]
        finally:
            governor_main.ollama_list_models = original_list

    def test_no_modify_analyzed_project(self, tmp_path):
        from governor.profile_benchmark import FIXTURE_DIR
        fixture = FIXTURE_DIR / "python_project"
        original = {}
        for f in fixture.rglob("*"):
            if f.is_file():
                original[str(f)] = f.read_text(encoding="utf-8")

        client = FakeClient([valid_json(str(f)) for f in fixture.rglob("*") if f.is_file()], model="safe")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        run_profile_benchmark(
            profiles=["python"],
            models=["safe"],
            max_tasks=10,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        for f in fixture.rglob("*"):
            if f.is_file():
                assert f.read_text(encoding="utf-8") == original[str(f)], f"{f} was modified"

    def test_model_recommendations_profile_uses_model_profiles(self, tmp_path):
        from governor.model_profiles import ModelProfileEvent

        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        store = mem.model_profile_store()
        for _ in range(20):
            store.record_task_result(ModelProfileEvent(
                model="py-best",
                task_type="inspect_code_file",
                profile="python",
                status="completed",
                json_valid=True,
                response_time_ms=50,
                input_chars=500,
                output_chars=200,
                current_max_chars=12000,
            ))

        from governor.model_recommendations import get_model_recommendations
        rec = get_model_recommendations(memory=mem, profile="python")
        assert rec.model == "py-best"
        assert rec.source == "model_profiles"

    def test_no_mcp_or_adapter_touch(self):
        import governor.profile_benchmark as pb
        source = Path(pb.__file__).read_text(encoding="utf-8")
        assert "mcp" not in source.lower()
        assert "openclaw" not in source.lower()
        assert "opencode" not in source.lower()

    def test_calibrate_models_dry_run_no_ollama(self):
        client = FakeClient([], model="calib")
        result = run_profile_benchmark(
            profiles=["python", "javascript"],
            models=["calib"],
            max_tasks=2,
            client=client,
            dry_run=True,
        )
        assert len(client.calls) == 0
        assert isinstance(result, BenchmarkDryRun)

    def test_calibrate_models_uses_profile_benchmark(self, tmp_path):
        client = FakeClient([valid_json("x")] * 9, model="calib")
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        report = run_profile_benchmark(
            profiles=["python", "javascript"],
            models=["calib"],
            max_tasks=1,
            client=client,
            memory=mem,
            output_dir=tmp_path / "benchmarks",
        )
        assert isinstance(report, ProfileBenchmarkReport)
        assert len(report.profiles) >= 2
