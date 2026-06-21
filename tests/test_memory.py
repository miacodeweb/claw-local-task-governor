from governor.memory import DEFAULT_RECOMMENDED_MAX_CHARS, SQLiteMemory


def test_memory_creates_tables_and_reuses_matching_result(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite")
    result = {
        "file": "main.py",
        "status": "ok",
        "risk": "none",
        "summary": "Clean.",
        "findings": [],
        "needs_related_file": False,
        "related_files": [],
    }

    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="main.py",
        file_hash="hash-1",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=True,
        json_repaired=False,
        risk="none",
        result_json=result,
    )

    reusable = memory.find_reusable_result(
        project_path="/project",
        file_path="main.py",
        file_hash="hash-1",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
    )

    assert reusable is not None
    assert reusable.result_json == result
    assert reusable.json_valid is True
    assert reusable.json_repaired is False


def test_memory_does_not_reuse_changed_hash(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite")
    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="main.py",
        file_hash="hash-1",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=True,
        json_repaired=False,
        risk="none",
        result_json={"file": "main.py"},
    )

    reusable = memory.find_reusable_result(
        project_path="/project",
        file_path="main.py",
        file_hash="hash-2",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
    )

    assert reusable is None


def test_memory_tracks_model_profile_counts(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite")
    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="good.py",
        file_hash="hash-1",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=True,
        json_repaired=True,
        risk="low",
        result_json={"file": "good.py"},
    )
    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="bad.py",
        file_hash="hash-2",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=False,
        json_repaired=False,
        risk="none",
        result_json=None,
    )

    with memory._connect() as connection:
        row = connection.execute(
            """
            SELECT success_count,
                   json_fail_count,
                   json_repair_count,
                   average_response_time,
                   recommended_max_chars
            FROM model_profiles
            """
        ).fetchone()

    assert row["success_count"] == 1
    assert row["json_fail_count"] == 1
    assert row["json_repair_count"] == 1
    assert row["average_response_time"] == 0
    assert row["recommended_max_chars"] < DEFAULT_RECOMMENDED_MAX_CHARS


def test_memory_tracks_response_time_and_recommended_max_chars(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite")

    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="good.py",
        file_hash="hash-1",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=True,
        json_repaired=False,
        risk="none",
        result_json={"file": "good.py"},
        response_time_seconds=2.0,
        current_max_chars=4000,
    )
    memory.save_task_result(
        project_path="/project",
        project_type="python",
        file_path="bad.py",
        file_hash="hash-2",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="file-analysis-v1",
        json_valid=False,
        json_repaired=False,
        risk="none",
        result_json=None,
        response_time_seconds=4.0,
        current_max_chars=4500,
    )

    profile = memory.get_model_profile("demo-model", "inspect_code_file")

    assert profile is not None
    assert profile.average_response_time == 3.0
    assert profile.recommended_max_chars == 3375
    assert memory.recommended_max_chars("demo-model", "inspect_code_file", fallback=9000) == 3375


def test_memory_lists_model_profiles(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite")
    memory.update_model_profile(
        model="demo-model",
        task_type="inspect_config_file",
        json_valid=True,
        json_repaired=False,
        response_time_seconds=1.5,
        current_max_chars=3000,
    )

    profiles = memory.list_model_profiles()

    assert len(profiles) == 1
    assert profiles[0].task_type == "inspect_config_file"
    assert profiles[0].success_count == 1
    assert profiles[0].recommended_max_chars == 3500
