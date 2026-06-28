"""Deterministic task priority scoring from scanner and optional Graphify signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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

RISK_PATH_PATTERNS = {
    ".env": 18,
    "auth": 10,
    "credential": 14,
    "login": 10,
    "password": 14,
    "payment": 10,
    "permission": 10,
    "secret": 14,
    "security": 10,
    "token": 12,
}


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
    graphify_signals: dict[str, dict[str, Any]] | None = None,
    profile_base_priority: str = "low",
    profile_risk_patterns: list[str] | None = None,
) -> tuple[str, int, list[str]]:
    """Return priority label, numeric score, and human-readable priority reasons."""
    graphify_signals = graphify_signals or {}
    reasons = [reason_for_task(task_type)]
    priority = priority_from_importance(scanned_file.get("importance"))
    score = PRIORITY_SCORE[priority]
    reasons.append(f"scanner: importance:{scanned_file.get('importance', 'low')}")

    base_priority_score, base_priority_reason = profile_base_priority_signal(profile_base_priority)
    score += base_priority_score
    reasons.append(base_priority_reason)

    type_score, type_reason = scanner_type_signal(task_type)
    score += type_score
    reasons.append(type_reason)

    size_score, size_reason = size_signal(int(scanned_file.get("size") or 0))
    score += size_score
    reasons.append(size_reason)

    risk_score, risk_reasons = scanner_risk_signals(scanned_file, profile_risk_patterns or [])
    score += risk_score
    reasons.extend(risk_reasons)

    if is_modified_signal(scanned_file):
        score += 20
        reasons.append("scanner: modified_file")

    graph_signal = graphify_signals.get(scanned_file["path"])
    if graph_signal:
        graph_score, graph_reasons = graphify_score(graph_signal)
        score += graph_score
        reasons.extend(graph_reasons)

    return priority_from_score(score), score, reasons


def scanner_type_signal(task_type: str) -> tuple[int, str]:
    if task_type == "inspect_config_file":
        return 15, "scanner: config_file"
    if task_type == "inspect_code_file":
        return 12, "scanner: source_code"
    if task_type == "inspect_documentation_file":
        return 4, "scanner: documentation"
    return 0, "scanner: generic_relevant_file"


def profile_base_priority_signal(base_priority: str) -> tuple[int, str]:
    normalized = str(base_priority or "low").lower()
    if normalized == "high":
        return 12, "profile: base_priority:high"
    if normalized == "medium":
        return 6, "profile: base_priority:medium"
    return 0, "profile: base_priority:low"


def size_signal(size: int) -> tuple[int, str]:
    if size <= 64 * 1024:
        return 8, "scanner: small_file"
    if size <= 512 * 1024:
        return 4, "scanner: medium_file"
    return -12, "scanner: large_file_safety_penalty"


def scanner_risk_signals(scanned_file: dict[str, Any], profile_patterns: list[str]) -> tuple[int, list[str]]:
    path = str(scanned_file.get("path") or "").replace("\\", "/").lower()
    filename = Path(path).name
    score = 0
    reasons = []
    for pattern, pattern_score in RISK_PATH_PATTERNS.items():
        if pattern in filename or f"/{pattern}" in path:
            score += pattern_score
            reasons.append(f"scanner: risk_pattern:{pattern}")
    for pattern in profile_patterns:
        normalized = str(pattern).lower()
        if normalized and (normalized in filename or normalized in path):
            score += 8
            reasons.append(f"profile: risk_pattern:{pattern}")
    return score, reasons


def is_modified_signal(scanned_file: dict[str, Any]) -> bool:
    return any(bool(scanned_file.get(key)) for key in ("modified", "changed", "changed_since_last_scan"))


def build_graphify_signals(graphify_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize Graphify context into per-file scoring hints."""
    signals: dict[str, dict[str, Any]] = {}

    for path in graphify_context.get("candidate_files", []):
        if isinstance(path, str) and path:
            _signal_for_path(signals, path)["referenced"] = True

    for node in graphify_context.get("nodes", []):
        if not isinstance(node, dict):
            continue
        paths = [node.get("path"), *node.get("related_paths", [])]
        for path in paths:
            if not path:
                continue
            existing = _signal_for_path(signals, str(path))
            existing["referenced"] = True
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

    if signal.get("referenced"):
        score += 6
        reasons.append("graphify: referenced_in_graph")

    if relationship_count >= 3:
        score += 20
        reasons.append("graphify: high_connectivity")
    elif relationship_count > 0:
        score += 10
        reasons.append("graphify: connected_node")

    if centrality >= 0.75:
        score += 20
        reasons.append("graphify: central_node")
    elif centrality > 0:
        score += 8
        reasons.append("graphify: centrality_signal")

    if signal.get("important"):
        score += 20
        reasons.append("graphify: important_node")

    if signal.get("module_related") or related_file_count > 1:
        score += 12
        reasons.append("graphify: related_module")

    return score, reasons


def reason_for_task(task_type: str) -> str:
    reasons = {
        "inspect_code_file": "source code file detected by project scanner",
        "inspect_config_file": "configuration file detected by project scanner",
        "inspect_documentation_file": "documentation file detected by project scanner",
        "inspect_unknown_file": "relevant file detected by project scanner",
    }
    return reasons[task_type]


def _signal_for_path(signals: dict[str, dict[str, Any]], path: str) -> dict[str, Any]:
    return signals.setdefault(
        path,
        {
            "referenced": False,
            "relationship_count": 0,
            "centrality": 0.0,
            "important": False,
            "related_file_count": 0,
            "module_related": False,
        },
    )
