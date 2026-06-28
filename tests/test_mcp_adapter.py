import json
from io import StringIO

from adapters.common.audit_response import AuditResponse
from adapters.mcp import server


def test_mcp_tools_registered():
    tools = server.list_tools()

    assert [tool["name"] for tool in tools] == [
        "localscope_audit",
        "localscope_status",
        "localscope_report",
        "localscope_graph_info",
    ]


def test_forbidden_tools_are_not_registered():
    names = {tool["name"] for tool in server.list_tools()}

    assert {"read_file", "write_file", "run_command", "apply_patch", "shell", "exec"}.isdisjoint(names)


def test_valid_request_returns_json_serializable_response(tmp_path, monkeypatch):
    def fake_run_audit(request, *, adapter):
        assert adapter == "mcp"
        assert request.path == str(tmp_path)
        return AuditResponse(
            status="completed",
            adapter="mcp",
            project_path=str(tmp_path),
            profile_detected="general",
            report_markdown="reports/audit.md",
            report_json="reports/audit.json",
            tasks_processed=1,
            json_valid=1,
            summary="ok",
        )

    monkeypatch.setattr(server, "run_audit", fake_run_audit)

    response = server.localscope_audit({"path": str(tmp_path), "max_tasks": 1})

    assert response["status"] == "completed"
    assert response["adapter"] == "mcp"
    assert response["tasks_processed"] == 1
    json.dumps(response)


def test_read_only_false_rejected(tmp_path):
    response = server.localscope_audit({"path": str(tmp_path), "read_only": False})

    assert response["status"] == "failed"
    assert response["adapter"] == "mcp"
    assert response["errors"] == ["read_only=false rejected"]


def test_missing_path_returns_structured_error(tmp_path):
    missing = tmp_path / "missing"

    response = server.localscope_audit({"path": str(missing)})

    assert response["status"] == "failed"
    assert response["adapter"] == "mcp"
    assert "does not exist" in response["summary"]
    json.dumps(response)


def test_quoted_existing_path_is_accepted(tmp_path, monkeypatch):
    def fake_run_audit(request, *, adapter):
        assert request.path == str(tmp_path)
        return AuditResponse(status="completed", adapter=adapter, project_path=request.path, summary="ok")

    monkeypatch.setattr(server, "run_audit", fake_run_audit)

    response = server.localscope_audit({"path": f'"{tmp_path}"'})

    assert response["status"] == "completed"


def test_empty_path_rejected():
    response = server.localscope_audit({"path": ""})

    assert response["status"] == "failed"
    assert response["summary"] == "path is required"


def test_invalid_max_tasks_rejected(tmp_path):
    response = server.localscope_audit({"path": str(tmp_path), "max_tasks": 0})

    assert response["status"] == "failed"
    assert "greater than 0" in response["summary"]


def test_excessive_max_tasks_rejected(tmp_path):
    response = server.localscope_audit({"path": str(tmp_path), "max_tasks": server.MAX_TASKS_LIMIT + 1})

    assert response["status"] == "failed"
    assert f"less than or equal to {server.MAX_TASKS_LIMIT}" in response["summary"]


def test_write_arguments_rejected(tmp_path):
    response = server.localscope_audit({"path": str(tmp_path), "write_file": "main.py"})

    assert response["status"] == "failed"
    assert "unsupported arguments" in response["summary"]
    assert "write_file" in response["summary"]


def test_shell_and_exec_arguments_rejected(tmp_path):
    shell_response = server.localscope_audit({"path": str(tmp_path), "shell": "dir"})
    exec_response = server.localscope_graph_info({"path": str(tmp_path), "exec": "dir"})

    assert shell_response["status"] == "failed"
    assert "shell" in shell_response["summary"]
    assert exec_response["status"] == "failed"
    assert "exec" in exec_response["summary"]


def test_ollama_unavailable_does_not_break_response(tmp_path, monkeypatch):
    def fake_run_audit(request, *, adapter):
        return AuditResponse.failed(adapter=adapter, project_path=request.path, summary="Ollama is not reachable")

    monkeypatch.setattr(server, "run_audit", fake_run_audit)

    response = server.localscope_audit({"path": str(tmp_path), "max_tasks": 1})

    assert response["status"] == "failed"
    assert response["adapter"] == "mcp"
    assert response["errors"] == ["Ollama is not reachable"]
    json.dumps(response)


def test_status_returns_json_serializable_response(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report_path = reports_dir / "audit-20260623-120000.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "summary": "Audit ok.",
                "totals": {"files_analyzed": 2, "json_failed": 0},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "LOCAL_REPORTS_DIR", reports_dir)

    response = server.localscope_status({"limit": 1})

    assert response["status"] == "completed"
    assert response["adapter"] == "mcp"
    assert response["audits_count"] == 1
    assert response["recent_audits"][0]["json_report_path"].endswith("audit-20260623-120000.json")
    assert "memory" in response
    json.dumps(response)


def test_report_with_missing_path_returns_structured_error(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(server, "LOCAL_REPORTS_DIR", reports_dir)

    response = server.localscope_report({"report_path": str(reports_dir / "audit-missing.json")})

    assert response["status"] == "failed"
    assert response["adapter"] == "mcp"
    assert response["errors"]
    json.dumps(response)


def test_report_rejects_path_outside_allowed_reports(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    outside = tmp_path / "audit-outside.json"
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "LOCAL_REPORTS_DIR", reports_dir)

    response = server.localscope_report({"report_path": str(outside)})

    assert response["status"] == "failed"
    assert "must be inside" in response["summary"]


def test_graph_info_works_without_graphify(tmp_path):
    response = server.localscope_graph_info({"path": str(tmp_path)})

    assert response["status"] == "completed"
    assert response["adapter"] == "mcp"
    assert response["available"] is False
    assert response["nodes_count"] == 0
    assert response["edges_count"] == 0
    assert response["important_files"] == []
    json.dumps(response)


def test_graph_info_works_with_graphify_fixture(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "main", "path": "src/main.py", "important": True, "centrality": 0.9},
                    {"id": "config", "path": "config/app.json"},
                ],
                "edges": [{"source": "main", "target": "config"}],
            }
        ),
        encoding="utf-8",
    )

    response = server.localscope_graph_info({"path": str(tmp_path)})

    assert response["status"] == "completed"
    assert response["available"] is True
    assert response["graph_path"].endswith("graph.json")
    assert response["nodes_count"] == 2
    assert response["edges_count"] == 1
    assert response["important_files"] == ["src/main.py"]


def test_tools_list_jsonrpc_response_contains_all_mcp_tools():
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert [tool["name"] for tool in response["result"]["tools"]] == [
        "localscope_audit",
        "localscope_status",
        "localscope_report",
        "localscope_graph_info",
    ]


def test_tools_call_returns_mcp_content_json(tmp_path, monkeypatch):
    def fake_run_audit(request, *, adapter):
        return AuditResponse(status="completed", adapter=adapter, project_path=request.path, summary="ok")

    monkeypatch.setattr(server, "run_audit", fake_run_audit)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "localscope_audit", "arguments": {"path": str(tmp_path)}},
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "completed"
    assert payload["adapter"] == "mcp"
    assert response["result"]["isError"] is False


def test_status_tool_call_returns_mcp_content_json(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(server, "LOCAL_REPORTS_DIR", reports_dir)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "localscope_status", "arguments": {}},
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "no_audits"
    assert payload["adapter"] == "mcp"
    assert response["result"]["isError"] is False


def test_protocol_stdout_is_line_delimited_json():
    input_stream = StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n')
    output_stream = StringIO()
    error_stream = StringIO()

    exit_code = server.serve(input_stream=input_stream, output_stream=output_stream, error_stream=error_stream)

    assert exit_code == 0
    assert error_stream.getvalue() == ""
    lines = output_stream.getvalue().splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["jsonrpc"] == "2.0"
    assert "tools" in decoded["result"]
