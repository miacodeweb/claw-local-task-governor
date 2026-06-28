import pytest

from governor.adaptive_limits import (
    AdaptiveLimitsConfig,
    decision_from_profile,
    resolve_effective_max_chars,
)
from governor.model_profiles import ModelProfileEvent, ModelProfileStore


def test_adaptive_limits_without_history_uses_default(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    config = AdaptiveLimitsConfig(default_max_chars=12000)

    decision = resolve_effective_max_chars(
        model="demo",
        task_type="inspect_code_file",
        profile="python",
        store=store,
        config=config,
        fixed_max_chars=9000,
    )

    assert decision.effective_max_chars == 12000
    assert decision.reason == "no_model_history"


def test_adaptive_limits_high_json_fail_reduces_max_chars(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="failed_json", json_valid=False, count=4, current_max_chars=10000)
    _record_many(store, status="completed", json_valid=True, count=2, current_max_chars=10000)
    stats = store.get_profile(model="demo", task_type="inspect_code_file")

    decision = decision_from_profile(stats, config=AdaptiveLimitsConfig(min_max_chars=4000))

    assert decision.effective_max_chars < stats.recommended_max_chars
    assert decision.reason.startswith("reduced:json_fail_rate")


def test_adaptive_limits_high_model_fail_reduces_max_chars(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="failed_model", json_valid=False, count=3, current_max_chars=10000)
    _record_many(store, status="completed", json_valid=True, count=3, current_max_chars=10000)
    stats = store.get_profile(model="demo", task_type="inspect_code_file")

    decision = decision_from_profile(stats, config=AdaptiveLimitsConfig(min_max_chars=4000))

    assert decision.effective_max_chars < stats.recommended_max_chars
    assert decision.reason.startswith("reduced:model_fail_rate")


def test_adaptive_limits_high_success_increases_gently(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="completed", json_valid=True, count=5, current_max_chars=10000)
    stats = store.get_profile(model="demo", task_type="inspect_code_file")

    decision = decision_from_profile(stats, config=AdaptiveLimitsConfig(hard_max_chars=20000))

    assert decision.effective_max_chars > stats.recommended_max_chars
    assert decision.reason.startswith("increased:success_rate")


def test_adaptive_limits_respects_min_max_chars(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="failed_json", json_valid=False, count=5, current_max_chars=4000)
    stats = store.get_profile(model="demo", task_type="inspect_code_file")

    decision = decision_from_profile(stats, config=AdaptiveLimitsConfig(min_max_chars=4000))

    assert decision.effective_max_chars == 4000


def test_adaptive_limits_respects_hard_max_chars(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="completed", json_valid=True, count=5, current_max_chars=20000)
    stats = store.get_profile(model="demo", task_type="inspect_code_file")

    decision = decision_from_profile(stats, config=AdaptiveLimitsConfig(hard_max_chars=20000))

    assert decision.effective_max_chars == 20000


def test_adaptive_limits_disabled_uses_fixed_value(tmp_path):
    store = ModelProfileStore(tmp_path / "memory.sqlite")
    _record_many(store, status="failed_json", json_valid=False, count=5, current_max_chars=8000)

    decision = resolve_effective_max_chars(
        model="demo",
        task_type="inspect_code_file",
        profile="general",
        store=store,
        config=AdaptiveLimitsConfig(default_max_chars=12000),
        fixed_max_chars=9000,
        enabled=False,
    )

    assert decision.effective_max_chars == 9000
    assert decision.enabled is False
    assert decision.reason == "adaptive_limits_disabled"


def _record_many(
    store: ModelProfileStore,
    *,
    status: str,
    json_valid: bool,
    count: int,
    current_max_chars: int,
) -> None:
    for _ in range(count):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                status=status,
                json_valid=json_valid,
                current_max_chars=current_max_chars,
            )
        )
