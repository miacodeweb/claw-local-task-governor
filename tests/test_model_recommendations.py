import json
import argparse
from pathlib import Path

import pytest

from governor import main as governor_main
from governor.model_profiles import (
    ModelProfileEvent,
    ModelProfileStore,
)
from governor.model_recommendations import (
    ModelRecommendation,
    get_model_recommendations,
    resolve_benchmark_model,
)
from governor.memory import SQLiteMemory
from governor.ollama_client import OllamaConfig


def write_benchmark_json(output_dir, models_data, summary=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"benchmark-{stamp}.json"
    path.write_text(json.dumps({
        "metadata": {"max_tasks": 3},
        "summary": summary or {
            "best_overall_model": "qwen",
            "best_json_model": "qwen",
            "fastest_model": "gemma4",
            "most_stable_model": "qwen",
        },
        "models": models_data,
        "prompt_versions": [{"version": "v1"}],
        "errors": [],
    }), encoding="utf-8")
    return path


def populate_model_profiles(memory, model="qwen", task_type="inspect_code_file", profile="general", runs=10):
    store = memory.model_profile_store()
    for _ in range(runs):
        store.record_task_result(ModelProfileEvent(
            model=model,
            task_type=task_type,
            profile=profile,
            status="completed",
            json_valid=True,
            response_time_ms=100,
            input_chars=500,
            output_chars=200,
            current_max_chars=12000,
        ))
    return store


class TestModelRecommendations:
    def test_recommendations_no_data_returns_safe_fallback(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        rec = get_model_recommendations(memory=memory)
        assert rec.source == "config.yaml"
        assert rec.confidence == "none"
        assert "no model profile" in rec.warnings[0]

    def test_recommendations_json_output_is_valid(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        rec = get_model_recommendations(memory=memory)
        data = rec.to_dict()
        assert json.dumps(data)
        assert "model" in data
        assert "confidence" in data
        assert "warnings" in data

    def test_recommendations_from_model_profiles(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(memory, model="qwen", runs=30)
        rec = get_model_recommendations(memory=memory)
        assert rec.model == "qwen"
        assert rec.source == "model_profiles"
        assert rec.confidence in ("medium", "high")

    def test_demo_model_is_filtered_from_real_recommendations(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(memory, model="demo-model", runs=30)
        rec = get_model_recommendations(memory=memory)
        assert rec.model != "demo-model"
        assert rec.source == "config.yaml"
        assert any("demo/test" in warning for warning in rec.warnings)

    def test_test_model_is_filtered_from_real_recommendations(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(memory, model="test-model", runs=30)
        rec = get_model_recommendations(memory=memory)
        assert rec.model != "test-model"
        assert rec.source == "config.yaml"

    def test_real_qwen_model_still_recommended(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(memory, model="demo-model", runs=30)
        populate_model_profiles(memory, model="qwen2.5-coder:7b", runs=20)
        rec = get_model_recommendations(memory=memory)
        assert rec.model == "qwen2.5-coder:7b"
        assert rec.source == "model_profiles"

    def test_include_demo_models_allows_debug_recommendation(self, tmp_path):
        memory = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(memory, model="demo-model", runs=30)
        rec = get_model_recommendations(memory=memory, include_demo_models=True)
        assert rec.model == "demo-model"
        assert rec.source == "model_profiles"

    def test_latest_benchmark_filters_demo_model(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        bench_dir = tmp_path / "benchmarks"
        write_benchmark_json(bench_dir, [
            {"model": "demo-model", "json_valid_rate": 1.0, "overall_score": 0.99},
            {"model": "qwen2.5-coder:7b", "json_valid_rate": 0.9, "overall_score": 0.8},
        ], summary={
            "best_overall_model": "demo-model",
            "best_json_model": "demo-model",
            "fastest_model": "demo-model",
            "most_stable_model": "demo-model",
        })

        rec = get_model_recommendations(
            memory=mem,
            latest_benchmark=True,
            benchmark_dir=bench_dir,
        )
        data = rec.to_dict()
        assert data["model"] == "qwen2.5-coder:7b"
        assert "demo-model" not in json.dumps(data)

    def test_recommendations_from_latest_benchmark(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        bench_dir = tmp_path / "benchmarks"
        write_benchmark_json(bench_dir, [
            {"model": "best-model", "json_valid_rate": 1.0, "overall_score": 0.9, "recommended_max_chars": 10000, "recommended_prompt_version": "v2_strict_json"},
            {"model": "other", "json_valid_rate": 0.5, "overall_score": 0.4},
        ], summary={
            "best_overall_model": "best-model",
            "best_json_model": "best-model",
            "fastest_model": "best-model",
            "most_stable_model": "best-model",
        })

        rec = get_model_recommendations(
            memory=mem,
            latest_benchmark=True,
            benchmark_dir=bench_dir,
        )
        assert rec.best_json_model == "best-model"
        assert rec.last_benchmark is not None

    def test_recommendations_benchmark_only_when_no_profiles(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        bench_dir = tmp_path / "benchmarks"
        write_benchmark_json(bench_dir, [
            {"model": "bench-only", "json_valid_rate": 1.0, "overall_score": 0.9, "recommended_max_chars": 8000, "recommended_prompt_version": "v3_short_schema"},
        ], summary={
            "best_overall_model": "bench-only",
            "best_json_model": "bench-only",
            "fastest_model": "bench-only",
            "most_stable_model": "bench-only",
        })

        rec = get_model_recommendations(
            memory=mem,
            latest_benchmark=True,
            benchmark_dir=bench_dir,
        )
        assert rec.model == "bench-only"
        assert rec.source == "benchmark"
        assert rec.max_chars == 8000
        assert rec.prompt_version == "v3_short_schema"

    def test_model_override_has_top_priority(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="recommended-model", runs=30)

        model, source = resolve_benchmark_model(
            model_override="explicit-model",
            use_benchmark_recommendations=False,
            config_model="config-model",
        )
        assert model == "explicit-model"
        assert "explicit_manual_override" in source

    def test_use_benchmark_recommendations_selects_recommended(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="best-model", runs=30)

        model, source = resolve_benchmark_model(
            model_override=None,
            use_benchmark_recommendations=True,
            config_model="config-model",
            memory=mem,
        )
        assert model == "best-model"
        assert "benchmark" in source

    def test_no_benchmark_falls_back_to_config(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        model, source = resolve_benchmark_model(
            model_override=None,
            use_benchmark_recommendations=True,
            config_model="config-placeholder",
            memory=mem,
        )
        # Falls back to config.yaml model since no benchmark/profiles exist
        assert source != "explicit_manual_override"
        assert "benchmark" not in source or "config.yaml" in source

    def test_model_recommendations_cli_no_benchmarks(self, capsys):
        exit_code = governor_main.main(["model-recommendations"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Model Recommendations" in output
        assert "Recommended model:" in output

    def test_model_recommendations_cli_json(self, capsys):
        exit_code = governor_main.main(["model-recommendations", "--json"])
        assert exit_code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "model" in data
        assert "source" in data

    def test_model_recommendations_cli_passes_include_demo_models(self, monkeypatch, capsys):
        captured = {}

        def fake_get_model_recommendations(**kwargs):
            captured.update(kwargs)
            return ModelRecommendation(
                model="demo-model" if kwargs["include_demo_models"] else "qwen2.5-coder:7b",
                prompt_version="v1",
                max_chars=12000,
                source="model_profiles",
                confidence="high",
                best_json_model=None,
                fastest_model=None,
                most_stable_model=None,
                last_benchmark=None,
                warnings=[],
            )

        monkeypatch.setattr(governor_main, "get_model_recommendations", fake_get_model_recommendations)

        exit_code = governor_main.main(["model-recommendations", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert data["model"] == "qwen2.5-coder:7b"
        assert captured["include_demo_models"] is False

        exit_code = governor_main.main(["model-recommendations", "--json", "--include-demo-models"])
        data = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert data["model"] == "demo-model"
        assert captured["include_demo_models"] is True

    def test_filter_by_task_type(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        store = mem.model_profile_store()
        store.record_task_result(ModelProfileEvent(
            model="code-model", task_type="inspect_code_file", profile="general",
            status="completed", json_valid=True, response_time_ms=100,
            input_chars=500, output_chars=200, current_max_chars=12000,
        ))
        store.record_task_result(ModelProfileEvent(
            model="config-model", task_type="inspect_config_file", profile="general",
            status="completed", json_valid=True, response_time_ms=100,
            input_chars=500, output_chars=200, current_max_chars=12000,
        ))
        rec = get_model_recommendations(memory=mem, task_type="inspect_config_file")
        assert rec.model == "config-model"

    def test_run_tasks_cli_passes_model_override(self, monkeypatch, capsys, tmp_path):
        captured_opts = {}

        class FakeSummary:
            dry_run = True
            tasks_requested = 1
            tasks_selected = 1
            dry_run_tasks = []
            model_used = ""
            benchmark_source = ""

        def fake_run_pending_tasks(*a, **kw):
            captured_opts["model_override"] = kw.get("model_override")
            captured_opts["use_benchmark_recommendations"] = kw.get("use_benchmark_recommendations")
            return FakeSummary()

        monkeypatch.setattr(governor_main, "run_pending_tasks", fake_run_pending_tasks)

        governor_main.main(["run-tasks", str(tmp_path), "--max-tasks", "1", "--model", "my-model", "--use-benchmark-recommendations", "--dry-run"])
        assert captured_opts["model_override"] == "my-model"
        assert captured_opts["use_benchmark_recommendations"] is True

    def test_confidence_none(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        rec = get_model_recommendations(memory=mem)
        assert rec.confidence == "none"
        assert rec.suggestion != ""

    def test_confidence_low_with_few_samples(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=3)
        rec = get_model_recommendations(memory=mem)
        assert rec.confidence == "low"
        assert "only 3 sample" in rec.warnings[0] or any("3 sample" in w for w in rec.warnings)
        assert rec.suggestion != ""

    def test_confidence_medium_with_enough_samples(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=10)
        rec = get_model_recommendations(memory=mem)
        assert rec.confidence == "medium"
        assert rec.model == "qwen"

    def test_confidence_high_with_many_samples(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=25)
        rec = get_model_recommendations(memory=mem)
        assert rec.confidence == "high"
        assert rec.model == "qwen"

    def test_low_confidence_warnings(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=2)
        rec = get_model_recommendations(memory=mem)
        assert rec.confidence == "low"
        assert any("2 sample" in w for w in rec.warnings)
        assert "benchmark-profile" in rec.suggestion

    def test_json_includes_confidence_and_warnings(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=3)
        rec = get_model_recommendations(memory=mem)
        data = rec.to_dict()
        assert data["confidence"] == "low"
        assert len(data["warnings"]) >= 1
        assert "suggestion" in data

    def test_suggestion_for_low_confidence(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        populate_model_profiles(mem, model="qwen", runs=1, profile="python")
        rec = get_model_recommendations(memory=mem, profile="python")
        assert "benchmark-profile" in rec.suggestion
        assert "python" in rec.suggestion

    def test_no_config_yaml_changed(self, tmp_path):
        import shutil
        config_path = Path("config.yaml")
        config_example = Path("config.example.yaml")
        if config_path.exists():
            original_mtime = config_path.stat().st_mtime
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        get_model_recommendations(memory=mem)
        if config_path.exists():
            assert config_path.stat().st_mtime == original_mtime
