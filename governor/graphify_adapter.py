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
    for output_dir in _candidate_output_dirs(project_path):
        artifacts = GraphifyArtifacts(
            graph_json=_file_path(output_dir / GRAPH_JSON),
            graph_report=_file_path(output_dir / GRAPH_REPORT),
            graph_html=_file_path(output_dir / GRAPH_HTML),
        )
        if artifacts.detected:
            return artifacts
    return GraphifyArtifacts(graph_json=None, graph_report=None, graph_html=None)


def detect_graphify_output(project_path: Path | str) -> dict[str, Any]:
    """Return a simple diagnostic dictionary for optional Graphify artifacts."""
    artifacts = detect_graphify_outputs(project_path)
    return {
        "available": artifacts.detected,
        "graph_json": artifacts.graph_json,
        "graph_report": artifacts.graph_report,
        "graph_html": artifacts.graph_html,
        "artifacts": {
            "graph_json": artifacts.graph_json,
            "graph_report": artifacts.graph_report,
            "graph_html": artifacts.graph_html,
        },
    }


def load_graph_json(project_path: Path | str) -> dict[str, Any] | None:
    """Load graphify-out/graph.json safely if it exists and is an object."""
    graph_data, _errors = _load_graph_json_with_errors(project_path)
    return graph_data


def get_graph_summary(project_path: Path | str) -> dict[str, Any]:
    """Build a defensive summary of Graphify data, if present."""
    artifacts = detect_graphify_outputs(project_path)
    graph_data, errors = _load_graph_json_with_errors(project_path)
    nodes = extract_relevant_nodes(graph_data, project_path) if graph_data else []
    edges = _extract_edges(graph_data) if graph_data else []
    referenced_files = sorted(
        {
            path
            for node in nodes
            for path in [node.get("path"), *node.get("related_paths", [])]
            if path
        }
    )
    important_nodes = _important_nodes(nodes)
    central_nodes = _central_nodes(nodes)
    high_connectivity_files = _high_connectivity_files(nodes)
    important_files = sorted({node["path"] for node in important_nodes if node.get("path")})
    relationships = _basic_relationships(edges)
    communities = _extract_communities(graph_data, project_path) if graph_data else []
    surprising_connections = _extract_surprising_connections(graph_data) if graph_data else []
    confidence = _extract_confidence(graph_data) if graph_data else None
    rationale = _extract_rationale(graph_data) if graph_data else ""
    warnings = list(errors)

    if artifacts.graph_json and graph_data and not nodes and not edges:
        warnings.append("graph.json was loaded but no recognizable nodes or edges were found")
    if artifacts.detected and not artifacts.graph_json:
        warnings.append("Graphify artifacts were found, but graph.json is missing")
    warnings.extend(_missing_referenced_file_warnings(project_path, referenced_files) if graph_data else [])

    return {
        "available": artifacts.detected,
        "detected": artifacts.detected,
        "used": bool(referenced_files),
        "graph_path": artifacts.graph_json,
        "graph_json": artifacts.graph_json,
        "graph_report": artifacts.graph_report,
        "graph_html": artifacts.graph_html,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "nodes_detected": len(nodes),
        "edges_detected": len(edges),
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "referenced_files": referenced_files,
        "candidate_files": referenced_files,
        "important_files": important_files,
        "important_nodes": important_nodes,
        "central_nodes": central_nodes,
        "high_connectivity_files": high_connectivity_files,
        "communities": communities,
        "modules": communities,
        "surprising_connections": surprising_connections,
        "confidence": confidence,
        "rationale": rationale,
        "relationships": relationships,
        "nodes": nodes,
        "warnings": warnings,
        "artifacts": {
            "graph_json": artifacts.graph_json,
            "graph_report": artifacts.graph_report,
            "graph_html": artifacts.graph_html,
        },
    }


def extract_relevant_nodes(graph_data: dict[str, Any], project_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Extract normalized candidate file nodes from common Graphify shapes."""
    nodes = _normalize_nodes(_extract_nodes(graph_data), project_path)
    relationship_counts = _relationship_counts(graph_data)
    relevant = []

    for node in nodes:
        path = node.get("path")
        if not path:
            continue
        node_id = str(node.get("id") or path)
        relevant.append(
            {
                "id": node_id,
                "path": path,
                "label": node.get("label") or Path(path).name,
                "type": node.get("type") or "file",
                "relationship_count": relationship_counts.get(node_id, 0),
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
            -int(bool(item["important"])),
            item["path"],
        ),
    )


def load_graphify_context(project_path: Path | str) -> dict[str, Any]:
    """Return optional Graphify context; never requires Graphify to be installed."""
    summary = get_graph_summary(project_path)
    return {
        "detected": summary["detected"],
        "used": summary["used"],
        "artifacts": summary["artifacts"],
        "nodes_total": summary["nodes_total"],
        "edges_total": summary["edges_total"],
        "graph_path": summary["graph_path"],
        "candidate_files": summary["candidate_files"],
        "important_files": summary["important_files"],
        "central_nodes": summary["central_nodes"],
        "high_connectivity_files": summary["high_connectivity_files"],
        "communities": summary["communities"],
        "surprising_connections": summary["surprising_connections"],
        "confidence": summary["confidence"],
        "rationale": summary["rationale"],
        "nodes": summary["nodes"],
        "warnings": summary["warnings"],
    }


def _candidate_output_dirs(project_path: Path | str) -> list[Path]:
    root = Path(project_path).expanduser()
    candidates = []
    if root.name == GRAPHIFY_DIR:
        candidates.append(root)
    candidates.append(root / GRAPHIFY_DIR)
    if root.parent != root:
        candidates.append(root.parent / GRAPHIFY_DIR)

    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _file_path(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def _load_graph_json_with_errors(project_path: Path | str) -> tuple[dict[str, Any] | None, list[str]]:
    artifacts = detect_graphify_outputs(project_path)
    if not artifacts.graph_json:
        return None, []

    graph_path = Path(artifacts.graph_json)
    try:
        loaded = json.loads(graph_path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        return None, [f"Could not read graph.json: {error}"]
    except json.JSONDecodeError as error:
        return None, [f"graph.json is invalid JSON: {error.msg} at line {error.lineno} column {error.colno}"]

    if not isinstance(loaded, dict):
        return None, ["graph.json was loaded but its root value is not a JSON object"]
    return loaded, []


def _extract_nodes(graph_data: dict[str, Any]) -> Any:
    for container in (graph_data, graph_data.get("graph"), graph_data.get("data")):
        if isinstance(container, dict):
            for key in ("nodes", "vertices", "items"):
                if key in container:
                    return container[key]
    return []


def _extract_edges(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_edges: Any = []
    for container in (graph_data, graph_data.get("graph"), graph_data.get("data")):
        if not isinstance(container, dict):
            continue
        for key in ("edges", "links", "relationships"):
            if key in container:
                raw_edges = container[key]
                break
        if raw_edges:
            break

    if isinstance(raw_edges, dict):
        raw_edges = raw_edges.values()
    if not isinstance(raw_edges, list):
        return []
    return [edge for edge in raw_edges if isinstance(edge, dict)]


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
    raw_path = _node_path_value(node, node_id)
    path = _normalize_path(str(raw_path), project_path) if raw_path else ""
    return {
        "id": node_id or path,
        "path": path,
        "label": str(node.get("label") or node.get("name") or Path(path).name),
        "type": str(node.get("type") or node.get("kind") or "file"),
        "centrality": node.get("centrality") or node.get("score") or node.get("rank") or 0,
        "important": _is_important_node(node),
        "related_paths": _related_paths(node, project_path),
    }


def _node_path_value(node: dict[str, Any], node_id: str) -> Any:
    for key in ("path", "file", "file_path", "filepath", "filename", "name"):
        value = node.get(key)
        if value:
            return value
    if _looks_like_path(node_id):
        return node_id
    label = str(node.get("label") or "")
    if _looks_like_path(label):
        return label
    return node_id


def _relationship_counts(graph_data: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in _extract_edges(graph_data):
        for endpoint_key in ("source", "target", "from", "to"):
            endpoint = _endpoint_id(edge.get(endpoint_key))
            if not endpoint:
                continue
            counts[endpoint] = counts.get(endpoint, 0) + 1
    return counts


def _important_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            node
            for node in nodes
            if node.get("important")
            or float(node.get("centrality") or 0) > 0
            or int(node.get("relationship_count") or 0) > 2
        ],
        key=lambda node: (
            -int(bool(node.get("important"))),
            -float(node.get("centrality") or 0),
            -int(node.get("relationship_count") or 0),
            str(node.get("path") or ""),
        ),
    )


def _central_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        node
        for node in _important_nodes(nodes)
        if float(node.get("centrality") or 0) >= 0.75
        or bool(node.get("important"))
        or int(node.get("relationship_count") or 0) >= 3
    ]


def _high_connectivity_files(nodes: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(node.get("path"))
            for node in nodes
            if node.get("path") and int(node.get("relationship_count") or 0) >= 3
        }
    )


def _extract_communities(graph_data: dict[str, Any], project_path: Path | str | None) -> list[dict[str, Any]]:
    raw_communities: Any = []
    for container in (graph_data, graph_data.get("graph"), graph_data.get("data"), graph_data.get("metadata")):
        if not isinstance(container, dict):
            continue
        for key in ("communities", "modules", "clusters", "groups"):
            if key in container:
                raw_communities = container[key]
                break
        if raw_communities:
            break

    if isinstance(raw_communities, dict):
        raw_communities = [
            dict(value, id=str(key)) if isinstance(value, dict) else {"id": str(key), "name": str(value)}
            for key, value in raw_communities.items()
        ]
    if not isinstance(raw_communities, list):
        return []

    communities = []
    for index, community in enumerate(raw_communities):
        if not isinstance(community, dict):
            continue
        raw_files = community.get("files") or community.get("members") or community.get("paths") or []
        files = []
        if isinstance(raw_files, list):
            for item in raw_files:
                if isinstance(item, dict):
                    raw_path = _node_path_value(item, "")
                else:
                    raw_path = item
                if raw_path:
                    files.append(_normalize_path(str(raw_path), project_path))
        communities.append(
            {
                "id": str(community.get("id") or community.get("name") or f"community-{index + 1}"),
                "name": str(community.get("name") or community.get("label") or community.get("id") or f"community-{index + 1}"),
                "files": sorted(set(files)),
                "size": int(community.get("size") or len(files)),
            }
        )
    return communities


def _extract_surprising_connections(graph_data: dict[str, Any]) -> list[dict[str, str]]:
    raw_values: Any = []
    for container in (graph_data, graph_data.get("graph"), graph_data.get("data"), graph_data.get("metadata")):
        if not isinstance(container, dict):
            continue
        for key in ("surprising_connections", "unexpected_connections", "anomalies"):
            if key in container:
                raw_values = container[key]
                break
        if raw_values:
            break
    if not isinstance(raw_values, list):
        return []
    normalized = []
    for item in raw_values[:100]:
        if isinstance(item, dict):
            normalized.append(
                {
                    "source": _endpoint_id(item.get("source") or item.get("from")),
                    "target": _endpoint_id(item.get("target") or item.get("to")),
                    "reason": str(item.get("reason") or item.get("rationale") or item.get("type") or "surprising connection"),
                }
            )
        else:
            normalized.append({"source": "", "target": "", "reason": str(item)})
    return normalized


def _extract_confidence(graph_data: dict[str, Any]) -> float | None:
    for container in (graph_data, graph_data.get("metadata"), graph_data.get("graph"), graph_data.get("data")):
        if not isinstance(container, dict):
            continue
        value = container.get("confidence")
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _extract_rationale(graph_data: dict[str, Any]) -> str:
    for container in (graph_data, graph_data.get("metadata"), graph_data.get("graph"), graph_data.get("data")):
        if not isinstance(container, dict):
            continue
        for key in ("rationale", "reason", "summary"):
            value = container.get(key)
            if value:
                return str(value)
    return ""


def _missing_referenced_file_warnings(project_path: Path | str, referenced_files: list[str]) -> list[str]:
    root = Path(project_path).expanduser()
    if not root.exists() or root.name == GRAPHIFY_DIR:
        return []
    warnings = []
    for file_path in referenced_files[:100]:
        if not (root / file_path).exists():
            warnings.append(f"Graphify referenced a missing path: {file_path}")
    return warnings


def _endpoint_id(endpoint: Any) -> str:
    if endpoint is None:
        return ""
    if isinstance(endpoint, dict):
        for key in ("id", "key", "path", "file", "name"):
            value = endpoint.get(key)
            if value:
                return str(value)
        return ""
    return str(endpoint)


def _basic_relationships(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    relationships = []
    for edge in edges[:100]:
        source = _endpoint_id(edge.get("source") or edge.get("from"))
        target = _endpoint_id(edge.get("target") or edge.get("to"))
        if not source and not target:
            continue
        relationships.append(
            {
                "source": source,
                "target": target,
                "type": str(edge.get("type") or edge.get("label") or "related"),
            }
        )
    return relationships


def _normalize_path(raw_path: str, project_path: Path | str | None) -> str:
    path_text = raw_path.replace("\\", "/").lstrip("./")
    path = Path(raw_path)
    if path.is_absolute() and project_path is not None:
        try:
            path_text = path.resolve().relative_to(Path(project_path).resolve()).as_posix()
        except (OSError, ValueError):
            path_text = path.name
    return path_text


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value or "." in Path(value).name


def _is_important_node(node: dict[str, Any]) -> bool:
    if bool(node.get("important") or node.get("is_important") or node.get("central")):
        return True
    priority = str(node.get("priority") or node.get("importance") or "").lower()
    if priority in {"high", "critical", "important", "central"}:
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
            raw_path = _node_path_value(value, "")
        else:
            raw_path = value
        if raw_path:
            paths.append(_normalize_path(str(raw_path), project_path))
    return sorted(set(paths))
