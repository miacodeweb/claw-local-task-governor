"""Generic microtask queue generation from scanner output."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from governor.graphify_adapter import load_graphify_context


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

PRIORITY_BY_IMPORTANCE = {
    "high": "high",
    "medium": "medium",
    "low": "low",
}

PRIORITY_SCORE = {
    "high": 70,
    "medium": 40,
    "low": 10,
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
    graphify: dict[str, Any]
    tasks: list[Task]

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "tasks_total": self.tasks_total,
            "tasks_pending": self.tasks_pending,
            "graphify": self.graphify,
            "tasks": [asdict(task) for task in self.tasks],
        }


def generate_tasks_from_scan_result(
    scan_result_path: Path | str,
    output_dir: Path | str = "reports",
) -> TaskQueue:
    """Create pending microtasks from an existing scan_result.json file."""
    scan_path = Path(scan_result_path)
    scan_result = json.loads(scan_path.read_text(encoding="utf-8"))
    graphify_context = load_graphify_context(scan_result["root"])
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
    }
    graphify_signals = build_graphify_signals(graphify_context)
    task_candidates = []

    for scanned_file in scan_result.get("files", []):
        if not scanned_file.get("relevant"):
            continue

        file_hash = scanned_file.get("sha256")
        if not file_hash:
            continue

        task_type = classify_task_type(scanned_file)
        priority, score, reasons = prioritize_task(scanned_file, task_type, graphify_signals)
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

    return TaskQueue(
        project_path=project_path,
        generated_at=created_at,
        profile=profile,
        tasks_total=len(tasks),
        tasks_pending=len(tasks),
        graphify={
            "detected": bool(graphify_context.get("detected")),
            "used": bool(graphify_context.get("used")),
            "nodes_total": int(graphify_context.get("nodes_total", 0)),
            "candidate_files": list(graphify_context.get("candidate_files", [])),
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


def priority_from_importance(importance: str | None) -> str:
    return PRIORITY_BY_IMPORTANCE.get(importance or "", "low")


def priority_from_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def prioritize_task(
    scanned_file: dict[str, Any],
    task_type: str,
    graphify_signals: dict[str, dict[str, Any]],
) -> tuple[str, int, list[str]]:
    reasons = [reason_for_task(task_type)]
    priority = priority_from_importance(scanned_file.get("importance"))
    score = PRIORITY_SCORE[priority]
    reasons.append(f"scanner importance {scanned_file.get('importance', 'low')}")

    type_score, type_reason = scanner_type_signal(task_type)
    score += type_score
    reasons.append(type_reason)

    size_score, size_reason = size_signal(int(scanned_file.get("size") or 0))
    score += size_score
    reasons.append(size_reason)

    if is_modified_signal(scanned_file):
        score += 20
        reasons.append("modified file signal")

    graph_signal = graphify_signals.get(scanned_file["path"])
    if graph_signal:
        graph_score, graph_reasons = graphify_score(graph_signal)
        score += graph_score
        reasons.extend(graph_reasons)

    return priority_from_score(score), score, reasons


def scanner_type_signal(task_type: str) -> tuple[int, str]:
    if task_type == "inspect_config_file":
        return 15, "configuration file signal"
    if task_type == "inspect_code_file":
        return 12, "source code signal"
    if task_type == "inspect_documentation_file":
        return 4, "documentation file signal"
    return 0, "generic relevant file signal"


def size_signal(size: int) -> tuple[int, str]:
    if size <= 64 * 1024:
        return 8, "small file signal"
    if size <= 512 * 1024:
        return 4, "medium file signal"
    return -12, "large file safety penalty"


def is_modified_signal(scanned_file: dict[str, Any]) -> bool:
    return any(bool(scanned_file.get(key)) for key in ("modified", "changed", "changed_since_last_scan"))


def build_graphify_signals(graphify_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    for node in graphify_context.get("nodes", []):
        if not isinstance(node, dict):
            continue
        paths = [node.get("path"), *node.get("related_paths", [])]
        for path in paths:
            if not path:
                continue
            existing = signals.setdefault(
                path,
                {
                    "relationship_count": 0,
                    "centrality": 0.0,
                    "important": False,
                    "related_file_count": 0,
                    "module_related": False,
                },
            )
            existing["relationship_count"] = max(
                int(existing["relationship_count"]),
                int(node.get("relationship_count") or 0),
            )
            existing["centrality"] = max(float(existing["centrality"]), float(node.get("centrality") or 0))
            existing["important"] = bool(existing["important"] or node.get("important"))
            related_count = int(node.get("related_file_count") or len(node.get("related_paths", [])))
            existing["related_file_count"] = max(int(existing["related_file_count"]), related_count)
            existing["module_related"] = bool(
                existing["module_related"]
                or str(node.get("type", "")).lower() in {"module", "package", "folder", "directory"}
                or related_count > 1
            )
    return signals


def graphify_score(signal: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    relationship_count = int(signal.get("relationship_count") or 0)
    centrality = float(signal.get("centrality") or 0)
    related_file_count = int(signal.get("related_file_count") or 0)

    if relationship_count >= 3:
        score += 20
        reasons.append(f"Graphify central node with {relationship_count} connections")
    elif relationship_count > 0:
        score += 10
        reasons.append(f"Graphify connected node with {relationship_count} connection(s)")

    if centrality >= 0.75:
        score += 20
        reasons.append("Graphify high centrality signal")
    elif centrality > 0:
        score += 8
        reasons.append("Graphify centrality signal")

    if signal.get("important"):
        score += 20
        reasons.append("Graphify important node signal")

    if signal.get("module_related") or related_file_count > 1:
        score += 12
        reasons.append(f"Graphify module relation signal for {related_file_count} file(s)")

    return score, reasons


def reason_for_task(task_type: str) -> str:
    reasons = {
        "inspect_code_file": "source code file detected by project scanner",
        "inspect_config_file": "configuration file detected by project scanner",
        "inspect_documentation_file": "documentation file detected by project scanner",
        "inspect_unknown_file": "relevant file detected by project scanner",
    }
    return reasons[task_type]
