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
            "graph_path": "/demo/graphify-out/graph.json",
            "nodes_total": 1,
            "edges_total": 4,
            "candidate_files": ["src/main.py"],
            "important_files": ["src/main.py"],
            "central_nodes": [{"path": "src/main.py"}],
            "high_connectivity_files": ["src/main.py"],
            "communities": [{"id": "core", "files": ["src/main.py"]}],
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
    assert queue.graphify["graph_path"] == "/demo/graphify-out/graph.json"
    assert queue.graphify["edges_total"] == 4
    assert queue.graphify["important_files"] == ["src/main.py"]
    assert queue.graphify["central_nodes"] == [{"path": "src/main.py"}]
    assert queue.tasks[0].priority == "high"
    assert "graphify: referenced_in_graph" in queue.tasks[0].reason
    assert "graphify: high_connectivity" in queue.tasks[0].reason
    assert "graphify: central_node" in queue.tasks[0].reason
    assert "graphify: important_node" in queue.tasks[0].reason
    assert queue.tasks_with_graphify_signal == 1


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
    assert "graphify: central_node" in queue.tasks[0].reason
    assert "scanner: modified_file" in queue.tasks[1].reason
    assert "graphify: related_module" in queue.tasks[1].reason


def test_prioritization_without_graphify_keeps_scanner_order():
    scan_result = {
        "root": "/demo",
        "profile_detected": "python",
        "files": [
            {"path": "README.md", "extension": ".md", "sha256": "doc", "relevant": True, "importance": "low", "size": 1000},
            {"path": "src/main.py", "extension": ".py", "sha256": "main", "relevant": True, "importance": "medium", "size": 2000},
            {"path": ".env.example", "extension": "", "sha256": "env", "relevant": True, "importance": "medium", "size": 200},
        ],
    }

    queue = build_task_queue(scan_result)

    assert [task.file_path for task in queue.tasks] == [".env.example", "src/main.py", "README.md"]
    assert queue.graphify["used"] is False
    assert queue.tasks_with_graphify_signal == 0
    assert "scanner: risk_pattern:.env" in queue.tasks[0].reason


def test_central_graphify_file_moves_ahead_of_unreferenced_file():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {"path": "src/helper.py", "extension": ".py", "sha256": "helper", "relevant": True, "importance": "medium", "size": 2000},
            {"path": "src/core.py", "extension": ".py", "sha256": "core", "relevant": True, "importance": "medium", "size": 2000},
        ],
    }

    queue = build_task_queue(
        scan_result,
        graphify_context={
            "detected": True,
            "used": True,
            "nodes_total": 1,
            "candidate_files": ["src/core.py"],
            "nodes": [
                {
                    "id": "core",
                    "path": "src/core.py",
                    "relationship_count": 5,
                    "centrality": 0.95,
                    "important": True,
                    "related_paths": [],
                    "related_file_count": 0,
                }
            ],
        },
    )

    assert [task.file_path for task in queue.tasks] == ["src/core.py", "src/helper.py"]
    assert "graphify: central_node" in queue.tasks[0].reason
    assert "graphify:" not in queue.tasks[1].reason


def test_unreferenced_file_keeps_normal_priority_when_graphify_exists():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {"path": "src/main.py", "extension": ".py", "sha256": "main", "relevant": True, "importance": "medium", "size": 2000},
            {"path": "src/unused.py", "extension": ".py", "sha256": "unused", "relevant": True, "importance": "medium", "size": 2000},
        ],
    }

    queue = build_task_queue(
        scan_result,
        graphify_context={
            "detected": True,
            "used": True,
            "nodes_total": 1,
            "candidate_files": ["src/main.py"],
            "nodes": [{"id": "main", "path": "src/main.py", "relationship_count": 1}],
        },
    )

    task_by_path = {task.file_path: task for task in queue.tasks}
    assert "graphify: referenced_in_graph" in task_by_path["src/main.py"].reason
    assert "graphify:" not in task_by_path["src/unused.py"].reason
    assert task_by_path["src/unused.py"].priority == "medium"


def test_partial_graphify_context_does_not_break_prioritization():
    scan_result = {
        "root": "/demo",
        "profile_detected": "general",
        "files": [
            {"path": "src/main.py", "extension": ".py", "sha256": "main", "relevant": True, "importance": "medium", "size": 2000},
        ],
    }

    queue = build_task_queue(
        scan_result,
        graphify_context={
            "detected": True,
            "used": False,
            "nodes_total": 0,
            "candidate_files": [],
            "nodes": [{"unexpected": "shape"}],
            "warnings": ["graph.json was loaded but no recognizable nodes or edges were found"],
        },
    )

    assert queue.tasks_total == 1
    assert queue.tasks[0].priority == "medium"
    assert queue.graphify["warnings"]
