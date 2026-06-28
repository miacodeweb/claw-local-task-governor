from governor.model_resolver import ResolvedModel, resolve_model
from governor.model_profiles import ModelProfileEvent
from governor.model_recommendations import get_model_recommendations
from governor.memory import SQLiteMemory


class TestModelResolver:
    def test_manual_override_wins(self, tmp_path):
        result = resolve_model(model_override="my-model", config_model="config-model")
        assert result.model == "my-model"
        assert result.source == "manual"
        assert result.confidence == "high"

    def test_benchmark_over_config_when_active(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        store = mem.model_profile_store()
        for _ in range(20):
            store.record_task_result(ModelProfileEvent(
                model="bench-best", task_type="inspect_code_file", profile="general",
                status="completed", json_valid=True, response_time_ms=50,
                input_chars=500, output_chars=200, current_max_chars=12000,
            ))
        rec = get_model_recommendations(memory=mem, latest_benchmark=True)
        result = resolve_model(
            use_benchmark_recommendations=True,
            config_model="config-model",
            recommendation=rec,
        )
        assert result.model == "bench-best"
        assert result.source == "benchmark"

    def test_config_over_default(self):
        result = resolve_model(use_benchmark_recommendations=False, config_model="my-config-model")
        assert result.model == "my-config-model"
        assert result.source == "config"

    def test_default_works_without_config(self):
        result = resolve_model(use_benchmark_recommendations=False, config_model=None)
        assert result.source == "default"
        assert result.model == "qwen2.5-coder:7b"

    def test_low_confidence_generates_warnings(self, tmp_path):
        mem = SQLiteMemory(tmp_path / "mem.sqlite")
        store = mem.model_profile_store()
        for _ in range(3):
            store.record_task_result(ModelProfileEvent(
                model="few-samples", task_type="inspect_code_file", profile="general",
                status="completed", json_valid=True, response_time_ms=100,
                input_chars=500, output_chars=200, current_max_chars=12000,
            ))
        rec = get_model_recommendations(memory=mem, latest_benchmark=True)
        result = resolve_model(
            use_benchmark_recommendations=True,
            config_model="cfg",
            recommendation=rec,
        )
        assert result.confidence in ("low", "medium")
        assert len(result.warnings) >= 1

    def test_manual_empty_string_falls_through(self):
        result = resolve_model(model_override="  ", config_model="cfg-model")
        assert result.model == "cfg-model"
        assert result.source == "config"

    def test_no_cycle_in_imports(self):
        import governor.model_resolver
        import governor.task_runner
        import governor.model_recommendations
        import governor.model_benchmark
        assert governor.model_resolver is not None
        assert governor.task_runner is not None
        assert governor.model_recommendations is not None
        assert governor.model_benchmark is not None

    def test_to_dict_contains_all_fields(self):
        result = resolve_model(model_override="x", config_model="y")
        d = result.to_dict()
        assert d["model"] == "x"
        assert d["source"] == "manual"
        assert "confidence" in d
        assert "benchmark_source" in d
        assert "warnings" in d
