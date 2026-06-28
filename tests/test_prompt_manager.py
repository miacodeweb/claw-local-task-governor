import json

from governor import main as governor_main
from governor.model_profiles import ModelProfileEvent, ModelProfileStore
from governor.prompt_manager import (
    DEFAULT_PROMPT_VERSION,
    SHORT_SCHEMA_VERSION,
    STRICT_JSON_VERSION,
    list_prompt_variants,
    recommend_prompt,
    resolve_prompt,
    select_prompt,
)


def test_prompt_manager_lists_available_variants():
    variants = list_prompt_variants()
    keys = {(variant.task_type, variant.version) for variant in variants}

    assert ("inspect_code_file", DEFAULT_PROMPT_VERSION) in keys
    assert ("inspect_code_file", STRICT_JSON_VERSION) in keys
    assert ("inspect_code_file", SHORT_SCHEMA_VERSION) in keys
    assert ("inspect_config_file", DEFAULT_PROMPT_VERSION) in keys


def test_prompt_manager_resolves_default_prompt():
    selection = resolve_prompt("inspect_code_file")

    assert selection.version == DEFAULT_PROMPT_VERSION
    assert selection.fallback_used is False
    assert selection.path.endswith("inspect_code_file.v1.txt")


def test_prompt_manager_resolves_prompt_by_version():
    selection = resolve_prompt("inspect_config_file", STRICT_JSON_VERSION)

    assert selection.version == STRICT_JSON_VERSION
    assert selection.path.endswith("inspect_config_file.v2_strict_json.txt")


def test_prompt_manager_falls_back_when_version_is_missing():
    selection = resolve_prompt("inspect_code_file", "v9_missing")

    assert selection.version == DEFAULT_PROMPT_VERSION
    assert selection.fallback_used is True
    assert selection.reason == "fallback:v9_missing_not_found"


def test_prompt_manager_selects_strict_json_when_json_fail_rate_is_high(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    for _ in range(4):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                profile="python",
                prompt_version=DEFAULT_PROMPT_VERSION,
                status="failed_json",
                json_valid=False,
            )
        )

    selection = select_prompt(
        model="demo",
        task_type="inspect_code_file",
        profile="python",
        store=store,
    )

    assert selection.version == STRICT_JSON_VERSION
    assert selection.reason == "high_json_fail_rate"


def test_prompt_manager_selects_short_schema_when_model_fails(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    for _ in range(4):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                profile="python",
                prompt_version=DEFAULT_PROMPT_VERSION,
                status="failed_model",
                json_valid=False,
            )
        )

    selection = select_prompt(
        model="demo",
        task_type="inspect_code_file",
        profile="python",
        store=store,
    )

    assert selection.version == SHORT_SCHEMA_VERSION
    assert selection.reason == "context_or_model_failures"


def test_prompt_manager_recommends_best_historical_variant(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    for _ in range(3):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                profile="python",
                prompt_version=STRICT_JSON_VERSION,
                status="completed",
                json_valid=True,
            )
        )
    for _ in range(3):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                profile="python",
                prompt_version=DEFAULT_PROMPT_VERSION,
                status="failed_json",
                json_valid=False,
            )
        )

    selection = recommend_prompt(
        model="demo",
        task_type="inspect_code_file",
        profile="python",
        store=store,
    )

    assert selection.version == STRICT_JSON_VERSION
    assert selection.reason == f"best_historical:{STRICT_JSON_VERSION}"


def test_prompts_list_cli_outputs_json(capsys):
    exit_code = governor_main.main(["prompts", "list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    data = json.loads(output)
    assert any(
        item["task_type"] == "inspect_code_file" and item["version"] == STRICT_JSON_VERSION
        for item in data["prompts"]
    )


def test_prompts_recommend_cli_outputs_recommendation(monkeypatch, capsys):
    class FakeStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_profiles(self, *, model=None, task_type=None):
            return []

    monkeypatch.setattr(governor_main, "ModelProfileStore", FakeStore)

    exit_code = governor_main.main(
        ["prompts", "recommend", "--model", "demo", "--task-type", "inspect_code_file"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Prompt recommendation:" in output
    assert "prompt_version=v1" in output
