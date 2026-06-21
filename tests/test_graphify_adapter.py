import json

from governor.graphify_adapter import (
    detect_graphify_outputs,
    extract_relevant_nodes,
    load_graph_json,
    load_graphify_context,
)


def test_detects_graphify_outputs(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text("{}", encoding="utf-8")
    (output_dir / "GRAPH_REPORT.md").write_text("# Graph", encoding="utf-8")
    (output_dir / "graph.html").write_text("<html></html>", encoding="utf-8")

    artifacts = detect_graphify_outputs(tmp_path)

    assert artifacts.detected is True
    assert artifacts.graph_json is not None
    assert artifacts.graph_report is not None
    assert artifacts.graph_html is not None


def test_loads_graph_json_and_extracts_relevant_nodes(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    graph = {
        "nodes": [
            {"id": "a", "path": "src/main.py", "label": "main.py", "type": "file", "centrality": 0.9},
            {"id": "b", "file": "package.json", "label": "package.json", "importance": "high"},
            {"id": "m", "path": "src", "type": "module", "files": ["src/main.py", "src/util.py"]},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "m", "target": "a"}],
    }
    (output_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    loaded = load_graph_json(tmp_path)
    nodes = extract_relevant_nodes(loaded, tmp_path)

    assert loaded == graph
    assert nodes[0]["path"] == "src/main.py"
    assert {node["path"] for node in nodes} == {"src/main.py", "package.json", "src"}
    assert all("relationship_count" in node for node in nodes)
    assert next(node for node in nodes if node["path"] == "package.json")["important"] is True
    assert next(node for node in nodes if node["path"] == "src")["related_paths"] == ["src/main.py", "src/util.py"]


def test_graphify_context_includes_related_module_files(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    graph = {
        "nodes": [
            {
                "id": "module-a",
                "path": "src",
                "type": "module",
                "files": [{"path": "src/main.py"}, {"path": "src/service.py"}],
            }
        ]
    }
    (output_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    context = load_graphify_context(tmp_path)

    assert context["used"] is True
    assert context["candidate_files"] == ["src", "src/main.py", "src/service.py"]


def test_graphify_context_is_optional_when_missing(tmp_path):
    context = load_graphify_context(tmp_path)

    assert context["detected"] is False
    assert context["used"] is False
    assert context["candidate_files"] == []
