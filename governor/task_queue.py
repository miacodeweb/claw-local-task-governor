"""Generic microtask queue generation from scanner output."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governor.graphify_adapter import load_graphify_context
from governor.profiles import load_profile
from governor.prioritizer import build_graphify_signals, prioritize_task


TASK_TYPES = {
    "inspect_code_file",
    "inspect_config_file",
    "inspect_documentation_file",
    "inspect_unknown_file",
}

CODE_EXTENSIONS = {
    ".cs",
    ".css",
    ".go",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".ts",
    ".tsx",
}

CONFIG_EXTENSIONS = {
    ".json",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}

CONFIG_FILENAMES = {
    ".env",
    ".env.development",
    ".env.example",
    ".env.local",
    ".env.production",
    ".env.test",
    "Dockerfile",
    "build.gradle",
    "composer.json",
    "docker-compose.yml",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "wp-config.php",
}

DOCUMENTATION_EXTENSIONS = {
    ".md",
}


@dataclass(frozen=True)
class Task:
    task_id: str
    project_path: str
    file_path: str
    file_hash: str
    task_type: str
    profile: str
    priority: str
    reason: str
    status: str
    created_at: str


@dataclass(frozen=True)
class TaskQueue:
    project_path: str
    generated_at: str
    profile: str
    tasks_total: int
    tasks_pending: int
    tasks_by_priority: dict[str, int]
    tasks_with_graphify_signal: int
    graphify: dict[str, Any]
    tasks: list[Task]

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "tasks_total": self.tasks_total,
            "tasks_pending": self.tasks_pending,
            "tasks_by_priority": self.tasks_by_priority,
            "tasks_with_graphify_signal": self.tasks_with_graphify_signal,
            "graphify": self.graphify,
            "tasks": [asdict(task) for task in self.tasks],
        }


def generate_tasks_from_scan_result(
    scan_result_path: Path | str,
    output_dir: Path | str = "reports",
    use_graphify: bool = True,
) -> TaskQueue:
    """Create pending microtasks from an existing scan_result.json file."""
    scan_path = Path(scan_result_path)
    scan_result = json.loads(scan_path.read_text(encoding="utf-8"))
    graphify_context = load_graphify_context(scan_result["root"]) if use_graphify else None
    queue = build_task_queue(scan_result, graphify_context=graphify_context)
    write_tasks(queue, output_dir)
    return queue


def build_task_queue(scan_result: dict, graphify_context: dict[str, Any] | None = None) -> TaskQueue:
    """Build a task queue from a scanner result dictionary."""
    project_path = scan_result["root"]
    profile = scan_result.get("profile_detected", "general")
    created_at = datetime.now(timezone.utc).isoformat()
    graphify_context = graphify_context or {
        "detected": False,
        "used": False,
        "artifacts": {},
        "nodes_total": 0,
        "candidate_files": [],
        "nodes": [],
        "warnings": [],
    }
    graphify_signals = build_graphify_signals(graphify_context)
    profile_rules = load_profile(profile)
    task_candidates = []

    for scanned_file in scan_result.get("files", []):
        if not scanned_file.get("relevant"):
            continue

        file_hash = scanned_file.get("sha256")
        if not file_hash:
            continue

        task_type = classify_task_type(scanned_file)
        priority, score, reasons = prioritize_task(
            scanned_file,
            task_type,
            graphify_signals,
            profile_base_priority=profile_rules.base_priority,
            profile_risk_patterns=profile_rules.risk_patterns,
        )
        task_candidates.append(
            (
                -score,
                scanned_file["path"],
                Task(
                    task_id="",
                    project_path=project_path,
                    file_path=scanned_file["path"],
                    file_hash=file_hash,
                    task_type=task_type,
                    profile=profile,
                    priority=priority,
                    reason="; ".join(reasons),
                    status="pending",
                    created_at=created_at,
                ),
            )
        )

    tasks = [
        Task(
            task_id=f"task-{index + 1:04d}",
            project_path=task.project_path,
            file_path=task.file_path,
            file_hash=task.file_hash,
            task_type=task.task_type,
            profile=task.profile,
            priority=task.priority,
            reason=task.reason,
            status=task.status,
            created_at=task.created_at,
        )
        for index, (_, __, task) in enumerate(sorted(task_candidates, key=lambda item: (item[0], item[1])))
    ]
    tasks_by_priority = count_tasks_by_priority(tasks)
    tasks_with_graphify_signal = sum(1 for task in tasks if "graphify:" in task.reason)

    return TaskQueue(
        project_path=project_path,
        generated_at=created_at,
        profile=profile,
        tasks_total=len(tasks),
        tasks_pending=len(tasks),
        tasks_by_priority=tasks_by_priority,
        tasks_with_graphify_signal=tasks_with_graphify_signal,
        graphify={
            "detected": bool(graphify_context.get("detected")),
            "used": bool(graphify_context.get("used")),
            "graph_path": graphify_context.get("graph_path"),
            "nodes_total": int(graphify_context.get("nodes_total", 0)),
            "edges_total": int(graphify_context.get("edges_total", 0)),
            "candidate_files": list(graphify_context.get("candidate_files", [])),
            "important_files": list(graphify_context.get("important_files", [])),
            "central_nodes": list(graphify_context.get("central_nodes", [])),
            "high_connectivity_files": list(graphify_context.get("high_connectivity_files", [])),
            "communities": list(graphify_context.get("communities", [])),
            "surprising_connections": list(graphify_context.get("surprising_connections", [])),
            "confidence": graphify_context.get("confidence"),
            "rationale": graphify_context.get("rationale", ""),
            "warnings": list(graphify_context.get("warnings", [])),
        },
        tasks=tasks,
    )


def write_tasks(queue: TaskQueue, output_dir: Path | str = "reports") -> Path:
    """Write reports/tasks.json for a generated queue."""
    output_path = Path(output_dir) / "tasks.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(queue.to_dict(), indent=2), encoding="utf-8")
    return output_path


def classify_task_type(scanned_file: dict) -> str:
    """Map scanned file metadata to a generic task type."""
    path = Path(scanned_file["path"])
    extension = str(scanned_file.get("extension") or path.suffix).lower()

    if path.name in CONFIG_FILENAMES or extension in CONFIG_EXTENSIONS:
        return "inspect_config_file"
    if extension in DOCUMENTATION_EXTENSIONS:
        return "inspect_documentation_file"
    if extension in CODE_EXTENSIONS:
        return "inspect_code_file"
    return "inspect_unknown_file"


def count_tasks_by_priority(tasks: list[Task]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for task in tasks:
        counts[task.priority] = counts.get(task.priority, 0) + 1
    return counts
