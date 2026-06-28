import json

import pytest

from governor import main as governor_main
from governor.model_profiles import (
    DEFAULT_RECOMMENDED_MAX_CHARS,
    ModelProfileEvent,
    ModelProfileStats,
    ModelProfileStore,
)


def test_model_profiles_creates_advanced_table(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    with store._connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(model_profiles)").fetchall()
        }

    assert {
        "model",
        "provider",
        "task_type",
        "profile",
        "prompt_version",
        "runs_count",
        "success_count",
        "json_valid_count",
        "json_repaired_count",
        "json_failed_count",
        "model_failed_count",
        "read_failed_count",
        "truncated_count",
        "average_response_ms",
        "average_input_chars",
        "average_output_chars",
        "recommended_max_chars",
        "recommended_prompt_version",
        "last_error",
        "last_seen_at",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_model_profiles_inserts_first_metric(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            profile="python",
            prompt_version="file-analysis-v1",
            status="completed",
            json_valid=True,
            response_time_ms=250,
            input_chars=100,
            output_chars=50,
            current_max_chars=4000,
        )
    )

    assert stats.runs_count == 1
    assert stats.success_count == 1
    assert stats.json_valid_count == 1
    assert stats.average_response_ms == 250
    assert stats.average_input_chars == 100
    assert stats.average_output_chars == 50


def test_model_profiles_updates_existing_metrics(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    event = ModelProfileEvent(
        model="demo-model",
        task_type="inspect_code_file",
        profile="python",
        prompt_version="file-analysis-v1",
        status="completed",
        json_valid=True,
        response_time_ms=100,
        input_chars=10,
        output_chars=20,
    )

    store.record_task_result(event)
    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            profile="python",
            prompt_version="file-analysis-v1",
            status="completed",
            json_valid=True,
            response_time_ms=300,
            input_chars=30,
            output_chars=60,
        )
    )

    assert stats.runs_count == 2
    assert stats.success_count == 2
    assert stats.average_response_ms == 200
    assert stats.average_input_chars == 20
    assert stats.average_output_chars == 40


def test_model_profiles_calculates_success_and_json_valid_rates(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            status="completed",
            json_valid=True,
        )
    )
    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            status="failed_json",
            json_valid=False,
        )
    )

    assert stats.success_rate == pytest.approx(0.5)
    assert stats.json_valid_rate == pytest.approx(0.5)
    assert stats.json_fail_rate == pytest.approx(0.5)


def test_model_profiles_records_json_repaired(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_config_file",
            status="completed",
            json_valid=True,
            json_repaired=True,
        )
    )

    assert stats.json_repaired_count == 1
    assert stats.json_repair_rate == pytest.approx(1.0)


def test_model_profiles_records_json_failed(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_config_file",
            status="failed_json",
            json_valid=False,
            current_max_chars=DEFAULT_RECOMMENDED_MAX_CHARS,
        )
    )

    assert stats.json_failed_count == 1
    assert stats.json_fail_rate == pytest.approx(1.0)
    assert stats.recommended_max_chars < DEFAULT_RECOMMENDED_MAX_CHARS


def test_model_profiles_records_model_failed(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            status="failed_model",
            error="Ollama timeout",
        )
    )

    assert stats.model_failed_count == 1
    assert stats.model_fail_rate == pytest.approx(1.0)
    assert stats.last_error == "Ollama timeout"


def test_model_profiles_records_truncated(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")

    stats = store.record_task_result(
        ModelProfileEvent(
            model="demo-model",
            task_type="inspect_code_file",
            status="completed",
            json_valid=True,
            truncated=True,
        )
    )

    assert stats.truncated_count == 1
    assert stats.truncation_rate == pytest.approx(1.0)


def test_model_stats_cli_shows_human_output(monkeypatch, capsys):
    class FakeStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_profiles(self, *, model=None, task_type=None):
            assert model == "demo-model"
            assert task_type == "inspect_code_file"
            return [_demo_stats()]

    monkeypatch.setattr(governor_main, "ModelProfileStore", FakeStore)

    exit_code = governor_main.main(
        ["model-stats", "--model", "demo-model", "--task-type", "inspect_code_file"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Model profile stats:" in output
    assert "model=demo-model" in output
    assert "success_rate=1.00" in output


def test_model_stats_cli_json_outputs_valid_json(monkeypatch, capsys):
    class FakeStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_profiles(self, *, model=None, task_type=None):
            return [_demo_stats()]

    monkeypatch.setattr(governor_main, "ModelProfileStore", FakeStore)

    exit_code = governor_main.main(["model-stats", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed["profiles"][0]["model"] == "demo-model"
    assert parsed["profiles"][0]["json_valid_rate"] == 1.0


def test_model_stats_cli_shows_recommendations(monkeypatch, capsys):
    class FakeStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_profiles(self, *, model=None, task_type=None):
            return [_demo_stats()]

    monkeypatch.setattr(governor_main, "ModelProfileStore", FakeStore)

    exit_code = governor_main.main(["model-stats", "--recommendations"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "effective_max_chars=" in output
    assert "adaptive_reason=" in output


def test_model_stats_cli_handles_empty_database(monkeypatch, capsys):
    class FakeStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_profiles(self, *, model=None, task_type=None):
            return []

    monkeypatch.setattr(governor_main, "ModelProfileStore", FakeStore)

    exit_code = governor_main.main(["model-stats"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No model profile stats found." in output


def _demo_stats() -> ModelProfileStats:
    return ModelProfileStats(
        model="demo-model",
        provider="ollama",
        task_type="inspect_code_file",
        profile="python",
        prompt_version="file-analysis-v1",
        runs_count=1,
        success_count=1,
        json_valid_count=1,
        json_repaired_count=0,
        json_failed_count=0,
        model_failed_count=0,
        read_failed_count=0,
        truncated_count=0,
        average_response_ms=123.0,
        average_input_chars=100.0,
        average_output_chars=40.0,
        recommended_max_chars=12500,
        recommended_prompt_version="file-analysis-v1",
        last_error="",
        last_seen_at="2026-06-23T00:00:00+00:00",
        created_at="2026-06-23T00:00:00+00:00",
        updated_at="2026-06-23T00:00:00+00:00",
    )
