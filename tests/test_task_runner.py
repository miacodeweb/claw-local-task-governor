import json
from dataclasses import replace

import pytest

from governor.ollama_client import OllamaConfig, OllamaConnectionError
from governor.memory import SQLiteMemory
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
    output_dir.mkdir()
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


def make_task(project, task_id, file_path, task_type="inspect_code_file"):
    return {
        "task_id": task_id,
        "project_path": str(project),
        "file_path": file_path,
        "file_hash": "abc123",
        "task_type": task_type,
        "profile": "python",
        "priority": "medium",
        "reason": "test task",
        "status": "pending",
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


def test_run_pending_tasks_limits_work_and_writes_results(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "one.py").write_text("print('one')", encoding="utf-8")
    (project / "two.py").write_text("print('two')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(
        output_dir,
        project,
        [
            make_task(project, "task-0001", "one.py"),
            make_task(project, "task-0002", "two.py"),
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

    assert summary.tasks_loaded == 2
    assert summary.tasks_selected == 1
    assert summary.tasks_completed == 1
    assert summary.tasks_new == 1
    assert summary.tasks_reused == 0
    assert len(client.calls) == 1

    written = json.loads((output_dir / "task_results.json").read_text(encoding="utf-8"))
    assert written["tasks_selected"] == 1
    assert written["results"][0]["status"] == "completed"
    assert written["results"][0]["json_valid"] is True


def test_run_pending_tasks_marks_invalid_json_without_stopping(tmp_path):
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

    assert summary.tasks_completed == 1
    assert summary.tasks_failed == 1
    assert summary.tasks_new == 2
    assert summary.tasks_reused == 0
    assert [result.status for result in summary.results] == ["failed_json", "completed"]


def test_run_pending_tasks_repairs_simple_model_json(tmp_path):
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

    assert summary.results[0].status == "completed"
    assert summary.results[0].json_repaired is True


def test_run_pending_tasks_truncates_file_content_for_model(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("0123456789", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    client = FakeClient([valid_model_json("main.py")], max_chars_per_file=4)

    run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=make_memory(tmp_path),
    )

    assert client.calls[0]["text"] == "0123"
    assert "0123" in client.calls[0]["prompt"]
    assert "456789" not in client.calls[0]["prompt"]


def test_run_pending_tasks_uses_model_profile_recommended_max_chars(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("a" * 3000, encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    memory = make_memory(tmp_path)
    memory.update_model_profile(
        model="demo-model",
        task_type="inspect_code_file",
        json_valid=False,
        json_repaired=False,
        current_max_chars=2500,
    )
    client = FakeClient([valid_model_json("main.py")], max_chars_per_file=10000, model="demo-model")

    run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=client,
        memory=memory,
    )

    assert len(client.calls[0]["text"]) == 2000
    assert len(client.calls[0]["prompt"].split("File content:", 1)[1].strip()) == 2000
    profile = memory.get_model_profile("demo-model", "inspect_code_file")
    assert profile.success_count == 1
    assert profile.json_fail_count == 1
    assert profile.recommended_max_chars == 2500


def test_run_pending_tasks_marks_model_errors_and_continues(tmp_path):
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
    assert summary.tasks_failed == 1


def test_run_pending_tasks_rejects_paths_outside_project(tmp_path):
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

    assert summary.results[0].status == "failed_file"
    assert len(client.calls) == 0


def test_run_pending_tasks_reuses_unchanged_memory_on_second_run(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    output_dir = tmp_path / "reports"
    write_tasks(output_dir, project, [make_task(project, "task-0001", "main.py")])
    memory = make_memory(tmp_path)
    first_client = FakeClient([valid_model_json("main.py")])

    first = run_pending_tasks(
        project,
        max_tasks=1,
        output_dir=output_dir,
        client=first_client,
        memory=memory,
    )
    second_client = FakeClient([])
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
    assert len(second_client.calls) == 0


def test_run_pending_tasks_requires_positive_max_tasks(tmp_path):
    with pytest.raises(ValueError):
        run_pending_tasks(tmp_path, max_tasks=0, output_dir=tmp_path)
