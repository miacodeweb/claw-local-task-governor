"""Optional Graphify output reader for structural project context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GRAPHIFY_DIR = "graphify-out"
GRAPH_JSON = "graph.json"
GRAPH_REPORT = "GRAPH_REPORT.md"
GRAPH_HTML = "graph.html"


@dataclass(frozen=True)
class GraphifyArtifacts:
    graph_json: str | None
    graph_report: str | None
    graph_html: str | None

    @property
    def detected(self) -> bool:
        return any([self.graph_json, self.graph_report, self.graph_html])


def detect_graphify_outputs(project_path: Path | str) -> GraphifyArtifacts:
    """Detect known Graphify output files without running Graphify."""
    root = Path(project_path)
    output_dir = root / GRAPHIFY_DIR
    graph_json = output_dir / GRAPH_JSON
    graph_report = output_dir / GRAPH_REPORT
    graph_html = output_dir / GRAPH_HTML
    return GraphifyArtifacts(
        graph_json=str(graph_json) if graph_json.is_file() else None,
        graph_report=str(graph_report) if graph_report.is_file() else None,
        graph_html=str(graph_html) if graph_html.is_file() else None,
    )


def load_graph_json(project_path: Path | str) -> dict[str, Any] | None:
    """Load graphify-out/graph.json if it exists."""
    graph_path = Path(project_path) / GRAPHIFY_DIR / GRAPH_JSON
    if not graph_path.is_file():
        return None
    return json.loads(graph_path.read_text(encoding="utf-8"))


def extract_relevant_nodes(graph_data: dict[str, Any], project_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Extract normalized candidate file nodes from common Graphify shapes."""
    nodes = _normalize_nodes(graph_data.get("nodes", []), project_path)
    relationship_counts = _relationship_counts(graph_data)
    relevant = []

    for node in nodes:
        path = node.get("path")
        if not path:
            continue
        relevant.append(
            {
                "id": node.get("id") or path,
                "path": path,
                "label": node.get("label") or Path(path).name,
                "type": node.get("type") or "file",
                "relationship_count": relationship_counts.get(str(node.get("id") or path), 0),
                "centrality": float(node.get("centrality") or node.get("score") or 0),
                "important": bool(node.get("important")),
                "related_paths": list(node.get("related_paths", [])),
                "related_file_count": len(node.get("related_paths", [])),
            }
        )

    return sorted(
        relevant,
        key=lambda item: (
            -item["centrality"],
            -item["relationship_count"],
            -item["related_file_count"],
            item["path"],
        ),
    )


def load_graphify_context(project_path: Path | str) -> dict[str, Any]:
    """Return optional Graphify context; never requires Graphify to be installed."""
    root = Path(project_path)
    artifacts = detect_graphify_outputs(root)
    graph_data = load_graph_json(root)
    nodes = extract_relevant_nodes(graph_data, root) if graph_data else []
    candidate_files = sorted(
        {
            path
            for node in nodes
            for path in [node.get("path"), *node.get("related_paths", [])]
            if path
        }
    )

    return {
        "detected": artifacts.detected,
        "used": bool(candidate_files),
        "artifacts": {
            "graph_json": artifacts.graph_json,
            "graph_report": artifacts.graph_report,
            "graph_html": artifacts.graph_html,
        },
        "nodes_total": len(nodes),
        "candidate_files": candidate_files,
        "nodes": nodes,
    }


def _normalize_nodes(raw_nodes: Any, project_path: Path | str | None) -> list[dict[str, Any]]:
    if isinstance(raw_nodes, dict):
        iterable = []
        for node_id, node in raw_nodes.items():
            if isinstance(node, dict):
                item = dict(node)
                item.setdefault("id", node_id)
                iterable.append(item)
            else:
                iterable.append({"id": node_id, "label": str(node)})
    elif isinstance(raw_nodes, list):
        iterable = [node for node in raw_nodes if isinstance(node, dict)]
    else:
        iterable = []

    return [_normalize_node(node, project_path) for node in iterable]


def _normalize_node(node: dict[str, Any], project_path: Path | str | None) -> dict[str, Any]:
    node_id = str(node.get("id") or node.get("key") or node.get("name") or "")
    raw_path = node.get("path") or node.get("file") or node.get("file_path") or node.get("name") or node_id
    path = _normalize_path(str(raw_path), project_path)
    return {
        "id": node_id or path,
        "path": path,
        "label": str(node.get("label") or node.get("name") or Path(path).name),
        "type": str(node.get("type") or node.get("kind") or "file"),
        "centrality": node.get("centrality") or node.get("score") or 0,
        "important": _is_important_node(node),
        "related_paths": _related_paths(node, project_path),
    }


def _relationship_counts(graph_data: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in ("edges", "links", "relationships"):
        raw_edges = graph_data.get(key, [])
        if isinstance(raw_edges, dict):
            raw_edges = raw_edges.values()
        if not isinstance(raw_edges, list):
            continue
        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            for endpoint_key in ("source", "target", "from", "to"):
                endpoint = edge.get(endpoint_key)
                if endpoint is None:
                    continue
                endpoint_id = str(endpoint)
                counts[endpoint_id] = counts.get(endpoint_id, 0) + 1
    return counts


def _normalize_path(raw_path: str, project_path: Path | str | None) -> str:
    path_text = raw_path.replace("\\", "/").lstrip("./")
    path = Path(raw_path)
    if path.is_absolute() and project_path is not None:
        try:
            path_text = path.resolve().relative_to(Path(project_path).resolve()).as_posix()
        except ValueError:
            path_text = path.name
    return path_text


def _is_important_node(node: dict[str, Any]) -> bool:
    if bool(node.get("important")):
        return True
    priority = str(node.get("priority") or node.get("importance") or "").lower()
    if priority in {"high", "critical", "important"}:
        return True
    tags = node.get("tags") or node.get("labels") or []
    if isinstance(tags, str):
        tags = [tags]
    return any(str(tag).lower() in {"important", "central", "entrypoint"} for tag in tags)


def _related_paths(node: dict[str, Any], project_path: Path | str | None) -> list[str]:
    raw_values = []
    for key in ("files", "related_files", "children", "members"):
        value = node.get(key)
        if isinstance(value, list):
            raw_values.extend(value)

    paths = []
    for value in raw_values:
        if isinstance(value, dict):
            raw_path = value.get("path") or value.get("file") or value.get("file_path") or value.get("name")
        else:
            raw_path = value
        if raw_path:
            paths.append(_normalize_path(str(raw_path), project_path))
    return sorted(set(paths))
