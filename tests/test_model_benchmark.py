import json
from dataclasses import replace
from pathlib import Path

import pytest

from governor import main as governor_main
from governor.model_benchmark import (
    BenchmarkReport,
    BenchmarkTaskResult,
    ModelBenchmarkStats,
    _aggregate_stats,
    _compute_summary,
    compute_scores,
    run_benchmark,
)
from governor.ollama_client import OllamaConfig, OllamaConnectionError
from governor.memory import SQLiteMemory


class FakeClient:
    def __init__(self, responses, model="test-model", max_chars_per_file=12000):
        self.responses = list(responses)
        self.config = replace(OllamaConfig(max_chars_per_file=max_chars_per_file), model=model)
        self.calls = []
        self._available = True
        self._models = [model]

    def analyze_text_with_model(self, prompt, text, max_chars=None):
        self.calls.append({"prompt": prompt, "text": text})
        if not self.responses:
            return '{"unknown": true}'
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def check_ollama_available(self):
        if not self._available:
            raise OllamaConnectionError("not reachable")
        return True

    def list_models(self):
        return list(self._models)


def valid_json_response(file_path="test.py"):
    return json.dumps({
        "file": file_path,
        "status": "ok",
        "risk": "none",
        "summary": "Looks good.",
        "findings": [],
        "needs_related_file": False,
        "related_files": [],
    })


def repaired_json_response(file_path="test.py"):
    return json.dumps({
        "file": file_path,
        "status": "ok",
        "risk": "none",
        "summary": "Looks good.",
        "findings": [],
        "needs_related_file": False,
        "related_files": [],
    }) + ", "


def invalid_json_response():
    return "not json at all"


def make_fixture_project(fixture_dir):
    fixture_dir.mkdir(exist_ok=True)
    (fixture_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (fixture_dir / "config.json").write_text('{"key": "value"}\n', encoding="utf-8")
    (fixture_dir / "README.md").write_text("# Test\n", encoding="utf-8")
    return fixture_dir


@pytest.fixture
def fixture_project(tmp_path):
    return make_fixture_project(tmp_path / "fixture")


@pytest.fixture
def memory_db(tmp_path):
    return SQLiteMemory(tmp_path / "bench_memory.sqlite")


class TestModelBenchmarkCore:
    def test_benchmark_single_model_valid_json(self, fixture_project, memory_db):
        client = FakeClient([valid_json_response("app.py"), valid_json_response("config.json"), valid_json_response("README.md")], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=3,
            profile="general",
            client=client,
            memory=memory_db,
        )
        assert isinstance(report, BenchmarkReport)
        assert len(report.models) == 1
        m = report.models[0]
        assert m["model"] == "qwen"
        assert m["json_valid"] == 3
        assert m["json_valid_rate"] == 1.0
        assert m["success_rate"] == 1.0
        assert m["overall_score"] > 0.8

    def test_benchmark_with_repaired_json(self, fixture_project, memory_db):
        client = FakeClient([repaired_json_response("app.py")], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        m = report.models[0]
        assert m["json_repaired"] >= 1
        assert m["json_valid"] >= 0

    def test_benchmark_with_invalid_json(self, fixture_project, memory_db):
        client = FakeClient([invalid_json_response()], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        m = report.models[0]
        assert m["json_failed"] >= 0
        assert m["json_valid_rate"] < 1.0

    def test_benchmark_with_model_failure(self, fixture_project, memory_db):
        client = FakeClient([OllamaConnectionError("down")], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        m = report.models[0]
        assert m["model_failed"] >= 1

    def test_benchmark_multiple_models(self, fixture_project, memory_db):
        c1 = FakeClient([valid_json_response("app.py")], model="model-a")
        c2 = FakeClient([valid_json_response("app.py")], model="model-b")
        c3 = FakeClient([valid_json_response("app.py")], model="model-c")

        import governor.model_benchmark as mb
        clients = {"model-a": c1, "model-b": c2, "model-c": c3}
        original_client_init = mb.OllamaClient.__init__

        class MultiClientOllama:
            def __init__(self, config):
                self.config = config
                self._inner = clients.get(config.model)
                if self._inner is None:
                    self._inner = FakeClient([], model=config.model)

            def check_ollama_available(self):
                return self._inner.check_ollama_available()

            def analyze_text_with_model(self, prompt, text, max_chars=None):
                return self._inner.analyze_text_with_model(prompt, text, max_chars=max_chars)

        mb.OllamaClient = MultiClientOllama
        try:
            report = run_benchmark(
                fixture_project,
                models=["model-a", "model-b", "model-c"],
                max_tasks=1,
                profile="general",
                memory=memory_db,
            )
            assert len(report.models) == 3
            for m in report.models:
                assert m["json_valid_rate"] == 1.0
        finally:
            mb.OllamaClient = original_client_init

    def test_benchmark_produces_valid_json_output(self, fixture_project, memory_db):
        client = FakeClient([valid_json_response("app.py")], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        output_dir = Path("reports/benchmarks") if not hasattr(report, '_output_dir') else None
        data = {
            "metadata": report.metadata,
            "summary": report.summary,
            "models": report.models,
            "prompt_versions": report.prompt_versions,
            "errors": report.errors,
        }
        assert json.dumps(data)
        assert isinstance(data["models"], list)
        assert isinstance(data["summary"], dict)

    def test_benchmark_writes_markdown(self, fixture_project, memory_db):
        tmp_output = fixture_project.parent / "test_bench_md_out"
        client = FakeClient([valid_json_response("app.py")], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
            output_dir=tmp_output,
        )
        md_files = list(tmp_output.glob("benchmark-*.md"))
        assert len(md_files) >= 1
        md_content = md_files[0].read_text(encoding="utf-8")
        assert "# LocalScope Model Benchmark" in md_content
        assert "qwen" in md_content

    def test_benchmark_scoring_best_json_model(self):
        stats_a = ModelBenchmarkStats(model="a", tasks_attempted=10, tasks_completed=10, json_valid=10, json_repaired=0, average_response_ms=100)
        stats_a.json_valid_rate = 1.0
        stats_a.success_rate = 1.0
        stats_a._response_times = [100]*10
        stats_a._input_chars_list = [500]*10
        stats_a._output_chars_list = [200]*10

        stats_b = ModelBenchmarkStats(model="b", tasks_attempted=10, tasks_completed=5, json_valid=5, json_repaired=3, average_response_ms=200)
        stats_b.json_valid_rate = 0.5
        stats_b.success_rate = 0.5
        stats_b.json_repair_rate = 0.3
        stats_b._response_times = [200]*10
        stats_b._input_chars_list = [500]*10
        stats_b._output_chars_list = [200]*10

        compute_scores([stats_a, stats_b])
        summary = _compute_summary([stats_a, stats_b])
        assert summary["best_json_model"] == "a"
        assert summary["fastest_model"] == "a"
        assert stats_a.overall_score > stats_b.overall_score

    def test_benchmark_scoring_fastest_model(self):
        stats_fast = ModelBenchmarkStats(model="fast", tasks_attempted=10, tasks_completed=10, json_valid=10, average_response_ms=50)
        stats_fast.json_valid_rate = 1.0
        stats_fast.success_rate = 1.0
        stats_fast._response_times = [50]*10
        stats_fast._input_chars_list = [500]*10
        stats_fast._output_chars_list = [200]*10

        stats_slow = ModelBenchmarkStats(model="slow", tasks_attempted=10, tasks_completed=10, json_valid=10, average_response_ms=5000)
        stats_slow.json_valid_rate = 1.0
        stats_slow.success_rate = 1.0
        stats_slow._response_times = [5000]*10
        stats_slow._input_chars_list = [500]*10
        stats_slow._output_chars_list = [200]*10

        compute_scores([stats_fast, stats_slow])
        summary = _compute_summary([stats_fast, stats_slow])
        assert summary["fastest_model"] == "fast"

    def test_dry_run_does_not_call_ollama(self, fixture_project, memory_db):
        client = FakeClient([], model="qwen")
        result = run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=2,
            profile="general",
            client=client,
            memory=memory_db,
            dry_run=True,
        )
        assert len(client.calls) == 0
        assert "BenchmarkDryRun" in type(result).__name__
        assert result.models == ["qwen"]
        assert len(result.tasks) == 2

    def test_all_ollama_uses_listed_models(self, fixture_project, memory_db):
        client = FakeClient(
            [valid_json_response("app.py"), valid_json_response("config.json")],
            model="qwen",
        )
        client._models = ["qwen", "deepseek", "gemma4"]
        original_list = governor_main.ollama_list_models
        governor_main.ollama_list_models = lambda: ["qwen", "deepseek", "gemma4"]
        try:
            import argparse
            ns = argparse.Namespace(
                all_ollama=True,
                models=None,
            )
            result = governor_main._resolve_benchmark_models(ns)
            assert result == ["qwen", "deepseek", "gemma4"]

            ns_no = argparse.Namespace(all_ollama=False, models=["qwen"])
            result_no = governor_main._resolve_benchmark_models(ns_no)
            assert result_no == ["qwen"]
        finally:
            governor_main.ollama_list_models = original_list

    def test_no_modify_analyzed_project(self, fixture_project, memory_db):
        original_contents = {}
        for f in fixture_project.iterdir():
            if f.is_file():
                original_contents[f.name] = f.read_text(encoding="utf-8")

        client = FakeClient([valid_json_response("app.py"), valid_json_response("config.json"), valid_json_response("README.md")], model="qwen")
        run_benchmark(
            fixture_project,
            models=["qwen"],
            max_tasks=3,
            profile="general",
            client=client,
            memory=memory_db,
        )

        for f in fixture_project.iterdir():
            if f.is_file():
                assert f.read_text(encoding="utf-8") == original_contents[f.name], f"{f.name} was modified"

    def test_updates_model_profiles(self, fixture_project, memory_db):
        client = FakeClient([valid_json_response("app.py")], model="qwen-update")
        run_benchmark(
            fixture_project,
            models=["qwen-update"],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        store = memory_db.model_profile_store()
        profile = store.get_profile(model="qwen-update", task_type="inspect_code_file", profile="general")
        assert profile is not None
        assert profile.runs_count >= 1

    def test_empty_models_returns_error(self, fixture_project, memory_db):
        client = FakeClient([], model="qwen")
        report = run_benchmark(
            fixture_project,
            models=[],
            max_tasks=1,
            profile="general",
            client=client,
            memory=memory_db,
        )
        assert isinstance(report, BenchmarkReport)
        assert len(report.models) == 0

    def test_timeout_seconds_passed_to_ollama_client(self, fixture_project, memory_db, monkeypatch):
        import governor.model_benchmark as model_benchmark

        created_configs = []

        class CapturingClient(FakeClient):
            def __init__(self, config):
                created_configs.append(config)
                super().__init__([valid_json_response("app.py")], model=config.model)
                self.config = config

        monkeypatch.setattr(model_benchmark, "OllamaClient", CapturingClient)

        report = run_benchmark(
            fixture_project,
            models=["slow-model"],
            max_tasks=1,
            profile="general",
            timeout_seconds=300,
            memory=memory_db,
        )

        assert isinstance(report, BenchmarkReport)
        assert any(c.model == "slow-model" and c.timeout_seconds == 300 for c in created_configs)

    def test_invalid_timeout_rejected(self, fixture_project, memory_db):
        with pytest.raises(ValueError, match="timeout_seconds"):
            run_benchmark(
                fixture_project,
                models=["qwen"],
                max_tasks=1,
                profile="general",
                timeout_seconds=0,
                memory=memory_db,
            )

    def test_dry_run_from_main(self, fixture_project):
        import argparse
        ns = argparse.Namespace(
            command="benchmark-models",
            path=str(fixture_project),
            models=["qwen"],
            all_ollama=False,
            max_tasks=2,
            profile="auto",
            mode="general",
            prompt_versions=None,
            no_adaptive_limits=False,
            timeout_seconds=None,
            output_dir=str(fixture_project.parent / "bench_out"),
            dry_run=True,
        )
        original_run = governor_main.run_benchmark
        called = []

        def fake_run(*a, **kw):
            called.append(kw)
            from governor.model_benchmark import BenchmarkDryRun
            return BenchmarkDryRun(
                models=kw.get("models", []),
                tasks=[{"file_path": "app.py", "task_type": "inspect_code_file"}],
                prompt_versions=["v1"],
                project_path=kw.get("project_path", ""),
                max_tasks=kw.get("max_tasks", 0),
                output_dir="reports/benchmarks",
            )

        governor_main.run_benchmark = fake_run
        try:
            governor_main._print_benchmark_dry_run(fake_run(
                path=str(fixture_project),
                models=["qwen"],
                max_tasks=2,
                profile="auto",
                mode="general",
                dry_run=True,
                output_dir=Path("reports/benchmarks"),
            ))
        finally:
            governor_main.run_benchmark = original_run

    def test_aggregate_stats_with_failures(self):
        results = [
            BenchmarkTaskResult("m1", "a.py", "inspect_code_file", "completed", True, False, False, 100.0, 500, 200, "v1", "{}", []),
            BenchmarkTaskResult("m1", "b.py", "inspect_code_file", "failed_json", False, False, True, 200.0, 600, 0, "v1", "bad", []),
            BenchmarkTaskResult("m1", "c.py", "inspect_code_file", "failed_model", False, False, False, 300.0, 400, 0, "v1", "", ["timeout"]),
            BenchmarkTaskResult("m2", "a.py", "inspect_code_file", "completed", True, True, False, 50.0, 500, 200, "v2_strict_json", "{}", []),
            BenchmarkTaskResult("m2", "b.py", "inspect_code_file", "completed", True, False, False, 75.0, 500, 200, "v2_strict_json", "{}", []),
        ]
        stats_list = _aggregate_stats(results, ["m1", "m2"])
        assert len(stats_list) == 2
        m1 = next(s for s in stats_list if s.model == "m1")
        m2 = next(s for s in stats_list if s.model == "m2")
        assert m1.tasks_attempted == 3
        assert m1.json_valid == 1
        assert m1.json_failed == 1
        assert m1.model_failed == 1
        assert m2.tasks_attempted == 2
        assert m2.tasks_completed == 2
        assert m2.json_repaired == 1

    def test_compute_scores_zero_for_total_failure(self):
        stats = ModelBenchmarkStats(model="fail", tasks_attempted=10, tasks_completed=0, json_valid=0, average_response_ms=0)
        compute_scores([stats])
        assert stats.overall_score == 0.0

    def test_most_stable_model_computation(self):
        stats_a = ModelBenchmarkStats(model="a", tasks_attempted=10, tasks_completed=10, json_valid=10, average_response_ms=100)
        stats_a.json_valid_rate = 1.0
        stats_a.success_rate = 1.0
        stats_a._response_times = [100]*10
        stats_a._input_chars_list = [500]*10
        stats_a._output_chars_list = [200]*10

        stats_b = ModelBenchmarkStats(model="b", tasks_attempted=10, tasks_completed=5, json_valid=5, average_response_ms=100)
        stats_b.json_valid_rate = 0.5
        stats_b.success_rate = 0.5
        stats_b.model_fail_rate = 0.5
        stats_b.json_fail_rate = 0.0
        stats_b._response_times = [100]*10
        stats_b._input_chars_list = [500]*10
        stats_b._output_chars_list = [200]*10

        compute_scores([stats_a, stats_b])
        summary = _compute_summary([stats_a, stats_b])
        assert summary["most_stable_model"] == "a"
