import json
from dataclasses import replace

import pytest

from governor.ollama_client import OllamaConfig, OllamaConnectionError
from governor.memory import SQLiteMemory
from governor.model_profiles import ModelProfileEvent
from governor.task_runner import run_pending_tasks


class FakeClient:
    def __init__(self, responses, max_chars_per_file=100, model="qwen2.5-coder:7b"):
        self.responses = list(responses)
        self.config = replace(OllamaConfig(max_chars_per_file=max_chars_per_file), model=model)
        self.calls = []

    def analyze_text_with_model(self, prompt, text):
        self.calls.append({"prompt": prompt, "text": text})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def write_tasks(output_dir, project, tasks):
    output_dir.mkdir(exist_ok=True)
    (output_dir / "tasks.json").write_text(
        json.dumps(
            {
                "project_path": str(project),
                "generated_at": "2026-06-21T00:00:00+00:00",
                "profile": "python",
                "tasks_total": len(tasks),
                "tasks_pending": len(tasks),
                "tasks": tasks,
            }
        ),
        encoding="utf-8",
    )


def make_task(
    project,
    task_id,
    file_path,
    task_type="inspect_code_file",
    status="pending",
    file_hash="abc123",
):
    return {
        "task_id": task_id,
        "project_path": str(project),
        "file_path": file_path,
        "file_hash": file_hash,
        "task_type": task_type,
        "profile": "python",
        "priority": "medium",
        "reason": "test task",
        "status": status,
        "created_at": "2026-06-21T00:00:00+00:00",
    }


def valid_model_json(file_path):
    return json.dumps(
        {
            "file": file_path,
            "status": "ok",
            "risk": "none",
            "summary": "No clear issues found.",
            "findings": [],
            "needs_related_file": False,
            "related_files": [],
        }
    )


def make_memory(tmp_path):
    return SQLiteMemory(tmp_path / "memory.sqlite")


def test_run_pending_tasks_writes_completed_result_with_valid_json(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")], model="demo-model")

    memory = make_memory(tmp_path)
    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=memory,
        prompt_version="v1",
    )

    assert summary.tasks_requested == 1
    assert summary.tasks_processed == 1
    assert summary.tasks_completed == 1
    assert summary.failed_json == 0
    assert len(client.calls) == 1
    assert "task-0001" in client.calls[0]["prompt"]

    written = json.loads((output_dir / "task_results.json").read_text(encoding="utf-8"))
    result = written["results"][0]
    assert result["task_id"] == "task-0001"
    assert result["file_path"] == "main.py"
    assert result["file_hash"] == "abc123"
    assert result["task_type"] == "inspect_code_file"
    assert result["profile"] == "python"
    assert result["status"] == "completed"
    assert result["json_valid"] is True
    assert result["json_repaired"] is False
    assert result["truncated"] is False
    assert result["model"] == "demo-model"
    assert result["raw_response"]
    assert result["result"]["file"] == "main.py"
    assert result["errors"] == []
    assert result["max_chars_used"] >= 1
    assert result["adaptive_limits_enabled"] is True
    assert result["adaptive_reason"]
    assert result["created_at"]
    assert summary.tasks_new == 1
    assert summary.tasks_reused == 0
    assert memory.find_reusable_result(
        project_path=str(project.resolve()),
        file_path="main.py",
        file_hash="abc123",
        task_type="inspect_code_file",
        model="demo-model",
        prompt_version="v1",
    ) is not None
    assert result["prompt_version"] == "v1"
    assert result["prompt_selected_reason"]


def test_run_pending_tasks_records_json_repair(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient(
        [
            """
            ```json
            {
              "file": "main.py",
              "status": "ok",
              "risk": "none",
              "summary": "No clear issues found.",
              "findings": [],
              "needs_related_file": false,
              "related_files": [],
            }
            ```
            """
        ]
    )

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert summary.tasks_completed == 1
    assert summary.json_repaired == 1
    assert summary.results[0].status == "completed"
    assert summary.results[0].json_repaired is True


def test_run_pending_tasks_marks_unrecoverable_json_and_continues(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "bad.py").write_text("print('bad')", encoding="utf-8")
    (project / "good.py").write_text("print('good')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(
        output_dir,
        project,
        [
            make_task(project, "task-0001", "bad.py"),
            make_task(project, "task-0002", "good.py"),
        ],
    )
    client = FakeClient(["not json", valid_model_json("good.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=2,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert [result.status for result in summary.results] == ["failed_json", "completed"]
    assert summary.tasks_completed == 1
    assert summary.failed_json == 1
    assert summary.tasks_failed == 1


def test_run_pending_tasks_marks_read_error_without_calling_ollama(tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside.py"
    project.mkdir()
    outside.write_text("print('outside')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "../outside.py")])
    client = FakeClient([valid_model_json("../outside.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert summary.results[0].status == "failed_read"
    assert summary.failed_read == 1
    assert len(client.calls) == 0


def test_run_pending_tasks_marks_model_error_and_continues(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "bad.py").write_text("print('bad')", encoding="utf-8")
    (project / "good.py").write_text("print('good')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(
        output_dir,
        project,
        [
            make_task(project, "task-0001", "bad.py"),
            make_task(project, "task-0002", "good.py"),
        ],
    )
    client = FakeClient([OllamaConnectionError("offline"), valid_model_json("good.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=2,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert [result.status for result in summary.results] == ["failed_model", "completed"]
    assert summary.failed_model == 1
    assert summary.tasks_failed == 1


def test_run_pending_tasks_respects_max_tasks_and_pending_only(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "one.py").write_text("print('one')", encoding="utf-8")
    (project / "two.py").write_text("print('two')", encoding="utf-8")
    (project / "done.py").write_text("print('done')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(
        output_dir,
        project,
        [
            make_task(project, "task-0001", "one.py"),
            make_task(project, "task-0002", "two.py"),
            make_task(project, "task-0003", "done.py", status="completed"),
        ],
    )
    client = FakeClient([valid_model_json("one.py"), valid_model_json("two.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert summary.tasks_loaded == 3
    assert summary.tasks_selected == 1
    assert summary.tasks_processed == 1
    assert [result.task_id for result in summary.results] == ["task-0001"]
    assert len(client.calls) == 1


def test_run_pending_tasks_accepts_tasks_json_with_utf8_bom(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    tasks_path = output_dir / "tasks.json"
    tasks_text = tasks_path.read_text(encoding="utf-8")
    tasks_path.write_text("\ufeff" + tasks_text, encoding="utf-8")
    client = FakeClient([valid_model_json("main.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert summary.tasks_completed == 1
    assert len(client.calls) == 1


def test_run_pending_tasks_truncates_file_content_and_records_it(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("0123456789", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")], max_chars_per_file=4)

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
        no_adaptive_limits=True,
    )

    assert client.calls[0]["text"] == "0123"
    assert "0123" in client.calls[0]["prompt"]
    assert "456789" not in client.calls[0]["prompt"]
    assert summary.results[0].truncated is True
    assert summary.results[0].max_chars_used == 4
    assert summary.results[0].adaptive_limits_enabled is False


def test_run_pending_tasks_uses_adaptive_limit_from_model_profile(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("x" * 9000, encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")], max_chars_per_file=10000, model="demo")
    memory = make_memory(tmp_path)
    store = memory.model_profile_store()
    for _ in range(4):
        store.record_task_result(
            ModelProfileEvent(
                model="demo",
                task_type="inspect_code_file",
                profile="python",
                status="failed_json",
                json_valid=False,
                current_max_chars=5000,
            )
        )

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=memory,
        prompt_version="v1",
    )

    assert len(client.calls[0]["text"]) == 4000
    assert summary.results[0].max_chars_used == 4000
    assert summary.results[0].adaptive_limits_enabled is True
    assert summary.results[0].adaptive_reason.startswith("reduced:json_fail_rate")


def test_run_pending_tasks_supports_documentation_and_unknown_prompts(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo", encoding="utf-8")
    (project / "sample.txt").write_text("notes", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(
        output_dir,
        project,
        [
            make_task(project, "task-0001", "README.md", task_type="inspect_documentation_file"),
            make_task(project, "task-0002", "sample.txt", task_type="inspect_unknown_file"),
        ],
    )
    client = FakeClient([valid_model_json("README.md"), valid_model_json("sample.txt")])

    summary = run_pending_tasks(
        project,
        max_tasks=2,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert summary.tasks_completed == 2
    assert "documentation file" in client.calls[0]["prompt"]
    assert "unknown category" in client.calls[1]["prompt"]


def test_run_pending_tasks_reuses_matching_memory_without_calling_ollama(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    memory = make_memory(tmp_path)

    first_client = FakeClient([valid_model_json("main.py")], model="demo-model")
    first = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=first_client,
        memory=memory,
    )
    second_client = FakeClient([], model="demo-model")
    second = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=second_client,
        memory=memory,
    )

    assert first.tasks_new == 1
    assert first.tasks_reused == 0
    assert second.tasks_new == 0
    assert second.tasks_reused == 1
    assert second.results[0].status == "reused"
    assert second.tasks_completed == 0
    assert len(second_client.calls) == 0


def test_run_pending_tasks_does_not_reuse_when_hash_changes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    memory = make_memory(tmp_path)
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py", file_hash="hash-1")])
    first_client = FakeClient([valid_model_json("main.py")], model="demo-model")
    run_pending_tasks(project, max_tasks=1, output_dir=output_dir, client=first_client, memory=memory)

    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py", file_hash="hash-2")])
    second_client = FakeClient([valid_model_json("main.py")], model="demo-model")
    second = run_pending_tasks(project, max_tasks=1, output_dir=output_dir, client=second_client, memory=memory)

    assert second.tasks_reused == 0
    assert second.tasks_new == 1
    assert len(second_client.calls) == 1


def test_run_pending_tasks_does_not_reuse_when_model_changes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    memory = make_memory(tmp_path)

    first_client = FakeClient([valid_model_json("main.py")], model="model-a")
    run_pending_tasks(project, max_tasks=1, output_dir=output_dir, client=first_client, memory=memory)
    second_client = FakeClient([valid_model_json("main.py")], model="model-b")
    second = run_pending_tasks(project, max_tasks=1, output_dir=output_dir, client=second_client, memory=memory)

    assert second.tasks_reused == 0
    assert second.tasks_new == 1
    assert len(second_client.calls) == 1


def test_run_pending_tasks_no_memory_ignores_cache_but_saves_new_result(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    memory = make_memory(tmp_path)

    first_client = FakeClient([valid_model_json("main.py")], model="demo-model")
    run_pending_tasks(project, max_tasks=1, output_dir=output_dir, client=first_client, memory=memory)
    second_client = FakeClient([valid_model_json("main.py")], model="demo-model")
    second = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=second_client,
        memory=memory,
        no_memory=True,
    )

    assert second.tasks_reused == 0
    assert second.tasks_new == 1
    assert len(second_client.calls) == 1


def test_run_pending_tasks_dry_run_does_not_call_ollama_or_write_results(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        dry_run=True,
    )

    assert summary.dry_run is True
    assert summary.tasks_processed == 1
    assert summary.results == []
    assert summary.dry_run_tasks[0].valid_path is True
    assert summary.dry_run_tasks[0].prompt_preview
    assert len(client.calls) == 0
    assert not (output_dir / "task_results.json").exists()


def test_run_pending_tasks_can_force_profile_for_selected_tasks(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")])

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
        profile_override="javascript",
    )

    assert summary.results[0].profile == "javascript"
    assert "Project profile:\njavascript" in client.calls[0]["prompt"]


def test_run_pending_tasks_manual_prompt_version_has_priority(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")], model="demo-model")

    summary = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
        prompt_version="v2_strict_json",
    )

    assert summary.results[0].prompt_version == "v2_strict_json"
    assert summary.results[0].prompt_selected_reason == "manual_prompt_version"
    assert "Return JSON only. No markdown." in client.calls[0]["prompt"]


def test_run_pending_tasks_requires_positive_max_tasks(tmp_path):
    with pytest.raises(ValueError):
        run_pending_tasks(tmp_path, max_tasks=0, output_dir=tmp_path)
