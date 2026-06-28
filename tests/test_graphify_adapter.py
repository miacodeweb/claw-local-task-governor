import json

from governor.graphify_adapter import (
    detect_graphify_output,
    detect_graphify_outputs,
    extract_relevant_nodes,
    get_graph_summary,
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


def test_detect_graphify_output_reports_unavailable_when_missing(tmp_path):
    diagnostic = detect_graphify_output(tmp_path)
    summary = get_graph_summary(tmp_path)

    assert diagnostic["available"] is False
    assert summary["available"] is False
    assert summary["nodes_detected"] == 0
    assert summary["referenced_files"] == []
    assert summary["warnings"] == []


def test_get_graph_summary_handles_valid_graph_json(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    graph = {
        "nodes": [
            {"id": "main", "path": "src/main.py", "centrality": 0.8},
            {"id": "config", "file_path": "config/app.json", "important": True},
        ],
        "links": [{"source": "main", "target": "config", "type": "imports"}],
    }
    (output_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    summary = get_graph_summary(tmp_path)

    assert summary["available"] is True
    assert summary["nodes_detected"] == 2
    assert summary["edges_detected"] == 1
    assert summary["referenced_files"] == ["config/app.json", "src/main.py"]
    assert summary["important_nodes"][0]["path"] == "config/app.json"
    assert summary["relationships"] == [{"source": "main", "target": "config", "type": "imports"}]


def test_get_graph_summary_extracts_deep_context_signals(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.py").write_text("print('core')\n", encoding="utf-8")
    (tmp_path / "src" / "api.py").write_text("print('api')\n", encoding="utf-8")
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    graph = {
        "metadata": {
            "confidence": 0.86,
            "rationale": "Graphify found a central application module.",
            "communities": [{"id": "backend", "files": ["src/core.py", "src/api.py"]}],
            "surprising_connections": [
                {"source": "src/core.py", "target": "config/prod.json", "reason": "runtime config access"}
            ],
        },
        "nodes": [
            {"id": "core", "path": "src/core.py", "centrality": 0.95, "important": True},
            {"id": "api", "path": "src/api.py"},
            {"id": "missing", "path": "config/prod.json"},
        ],
        "edges": [
            {"source": "core", "target": "api"},
            {"source": "core", "target": "missing"},
            {"source": "api", "target": "core"},
        ],
    }
    (output_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    summary = get_graph_summary(tmp_path)

    assert summary["available"] is True
    assert summary["graph_path"].endswith("graph.json")
    assert summary["nodes_count"] == 3
    assert summary["edges_count"] == 3
    assert summary["important_files"] == ["src/core.py"]
    assert summary["central_nodes"][0]["path"] == "src/core.py"
    assert summary["high_connectivity_files"] == ["src/core.py"]
    assert summary["communities"][0]["files"] == ["src/api.py", "src/core.py"]
    assert summary["surprising_connections"][0]["reason"] == "runtime config access"
    assert summary["confidence"] == 0.86
    assert "central application module" in summary["rationale"]
    assert any("config/prod.json" in warning for warning in summary["warnings"])


def test_get_graph_summary_handles_invalid_graph_json(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text("{invalid", encoding="utf-8")

    assert load_graph_json(tmp_path) is None
    summary = get_graph_summary(tmp_path)

    assert summary["available"] is True
    assert summary["nodes_detected"] == 0
    assert summary["referenced_files"] == []
    assert summary["warnings"]
    assert "invalid JSON" in summary["warnings"][0]


def test_load_graph_json_accepts_utf8_bom(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text('\ufeff{"nodes": [{"path": "README.md"}]}', encoding="utf-8")

    loaded = load_graph_json(tmp_path)

    assert loaded == {"nodes": [{"path": "README.md"}]}


def test_get_graph_summary_warns_for_unknown_minimal_structure(tmp_path):
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text(json.dumps({"metadata": {"tool": "graphify"}}), encoding="utf-8")

    summary = get_graph_summary(tmp_path)

    assert summary["available"] is True
    assert summary["nodes_detected"] == 0
    assert summary["edges_detected"] == 0
    assert summary["warnings"] == ["graph.json was loaded but no recognizable nodes or edges were found"]


def test_get_graph_summary_detects_nearby_parent_graphify_output(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    graph = {"graph": {"nodes": [{"id": "README.md", "label": "README.md"}]}}
    (output_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    summary = get_graph_summary(project_dir)

    assert summary["available"] is True
    assert summary["referenced_files"] == ["README.md"]
