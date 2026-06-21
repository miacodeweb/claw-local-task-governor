import json

from governor.scanner import scan_project
from governor.task_queue import (
    build_task_queue,
    classify_task_type,
    generate_tasks_from_scan_result,
)


def test_generates_pending_tasks_from_scan_result(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "package.json").write_text("{}", encoding="utf-8")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    (project / "image.png").write_bytes(b"skip")
    output_dir = tmp_path / "reports"

    scan_project(project, output_dir=output_dir)
    queue = generate_tasks_from_scan_result(
        output_dir / "scan_result.json",
        output_dir=output_dir,
    )

    assert queue.tasks_total == 3
    assert queue.tasks_pending == 3
    assert [task.task_id for task in queue.tasks] == ["task-0001", "task-0002", "task-0003"]
    assert {task.status for task in queue.tasks} == {"pending"}

    task_by_path = {task.file_path: task for task in queue.tasks}
    assert task_by_path["main.py"].task_type == "inspect_code_file"
    assert task_by_path["package.json"].task_type == "inspect_config_file"
    assert task_by_path["README.md"].task_type == "inspect_documentation_file"
    assert task_by_path["main.py"].file_hash

    tasks_json = json.loads((output_dir / "tasks.json").read_text(encoding="utf-8"))
    assert tasks_json["tasks_total"] == 3
    assert tasks_json["tasks"][0]["status"] == "pending"


def test_build_task_queue_skips_non_relevant_files():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {
                "path": "main.py",
                "extension": ".py",
                "sha256": "abc",
                "relevant": True,
                "importance": "medium",
            },
            {
                "path": "notes.txt",
                "extension": ".txt",
                "sha256": None,
                "relevant": False,
                "importance": "ignored",
            },
        ],
    }

    queue = build_task_queue(scan_result)

    assert queue.tasks_total == 1
    assert queue.tasks[0].file_path == "main.py"
    assert queue.tasks[0].priority == "medium"


def test_classifies_unknown_relevant_file():
    scanned_file = {
        "path": "custom.rules",
        "extension": ".rules",
        "sha256": "abc",
        "relevant": True,
        "importance": "low",
    }

    assert classify_task_type(scanned_file) == "inspect_unknown_file"


def test_build_task_queue_uses_graphify_candidates_to_boost_priority():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {"path": "src/main.py", "extension": ".py", "sha256": "abc", "relevant": True, "importance": "medium", "size": 2000},
        ],
    }

    queue = build_task_queue(
        scan_result,
        graphify_context={
            "detected": True,
            "used": True,
            "nodes_total": 1,
            "candidate_files": ["src/main.py"],
            "nodes": [
                {
                    "id": "main",
                    "path": "src/main.py",
                    "relationship_count": 4,
                    "centrality": 0.9,
                    "important": True,
                    "related_paths": [],
                    "related_file_count": 0,
                }
            ],
        },
    )

    assert queue.graphify["used"] is True
    assert queue.tasks[0].priority == "high"
    assert "Graphify central node" in queue.tasks[0].reason
    assert "Graphify important node" in queue.tasks[0].reason


def test_build_task_queue_orders_by_combined_scanner_and_graphify_score():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {"path": "docs/readme.md", "extension": ".md", "sha256": "doc", "relevant": True, "importance": "low", "size": 1000},
            {
                "path": "src/service.py",
                "extension": ".py",
                "sha256": "service",
                "relevant": True,
                "importance": "medium",
                "size": 2000,
                "changed_since_last_scan": True,
            },
            {"path": "src/main.py", "extension": ".py", "sha256": "main", "relevant": True, "importance": "medium", "size": 2000},
        ],
    }

    queue = build_task_queue(
        scan_result,
        graphify_context={
            "detected": True,
            "used": True,
            "nodes_total": 2,
            "candidate_files": ["src/main.py", "src/service.py"],
            "nodes": [
                {
                    "id": "module",
                    "path": "src",
                    "type": "module",
                    "relationship_count": 1,
                    "centrality": 0.2,
                    "important": False,
                    "related_paths": ["src/main.py", "src/service.py"],
                    "related_file_count": 2,
                },
                {
                    "id": "main",
                    "path": "src/main.py",
                    "type": "file",
                    "relationship_count": 4,
                    "centrality": 0.9,
                    "important": True,
                    "related_paths": [],
                    "related_file_count": 0,
                },
            ],
        },
    )

    assert [task.file_path for task in queue.tasks] == ["src/main.py", "src/service.py", "docs/readme.md"]
    assert queue.tasks[0].priority == "high"
    assert "Graphify high centrality signal" in queue.tasks[0].reason
    assert "modified file signal" in queue.tasks[1].reason
    assert "Graphify module relation signal" in queue.tasks[1].reason
