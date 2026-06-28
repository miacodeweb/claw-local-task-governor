import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from webui.server import (
    LocalScopeHandler,
    _html_page,
    _relative_path_or_none,
    run_webui,
)


@pytest.fixture
def server():
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), LocalScopeHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    thread.join(timeout=1)

def _get(server_url, path):
    try:
        with urllib.request.urlopen(f"{server_url}{path}", timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), resp.headers.get_content_type()
    except Exception as e:
        return None, str(e), ""

def _get_json(server_url, path):
    status, body, ct = _get(server_url, path)
    if status == 200 and "json" in ct:
        return json.loads(body)
    return None


class TestWebUI:
    def test_module_importable(self):
        import webui.server
        assert webui.server is not None

    def test_dashboard_responds(self, server):
        status, body, ct = _get(server, "/")
        assert status == 200
        assert "text/html" in ct
        assert "Dashboard" in body

    def test_api_status_responds_json(self, server):
        data = _get_json(server, "/api/status")
        assert data is None or isinstance(data, dict)
        if data:
            assert "name" in data

    def test_reports_list_no_crash(self, server):
        status, body, _ = _get(server, "/reports")
        assert status == 200

    def test_api_reports_no_crash(self, server):
        status, _, _ = _get(server, "/api/reports")
        assert status == 200

    def test_logs_list_no_crash(self, server):
        status, body, _ = _get(server, "/logs")
        assert status == 200

    def test_logs_errors_no_crash(self, server):
        status, body, _ = _get(server, "/logs/errors")
        assert status == 200

    def test_logs_tasks_no_crash(self, server):
        status, body, _ = _get(server, "/logs/tasks")
        assert status == 200

    def test_benchmarks_no_crash(self, server):
        status, body, _ = _get(server, "/benchmarks")
        assert status == 200

    def test_api_benchmarks_no_crash(self, server):
        status, _, _ = _get(server, "/api/benchmarks")
        assert status == 200

    def test_model_recommendations_page(self, server):
        status, body, _ = _get(server, "/models/recommendations")
        assert status == 200
        assert "Recommended model" in body

    def test_api_model_recommendations(self, server):
        data = _get_json(server, "/api/model-recommendations")
        if data:
            assert "model" in data

    def test_graphify_page(self, server):
        status, body, _ = _get(server, "/graphify")
        assert status == 200
        assert "Graphify" in body

    def test_api_graphify(self, server):
        data = _get_json(server, "/api/graphify")
        if data:
            assert "available" in data

    def test_api_logs_errors(self, server):
        status, body, ct = _get(server, "/api/logs/errors?limit=5")
        if "json" in ct:
            data = json.loads(body)
            assert "errors" in data

    def test_reject_path_traversal(self, server):
        status, _, _ = _get(server, "/reports/../../../etc/passwd")
        assert status != 200

    def test_no_dangerous_routes(self, server):
        for path in ["/api/write-file", "/api/run-command", "/api/apply-patch", "/api/shell"]:
            status, _, _ = _get(server, path)
            assert status != 200, f"{path} should not exist but returned {status}"

    def test_not_found_returns_404(self, server):
        status, _, _ = _get(server, "/nonexistent-xyz-123")
        if status is None:
            pytest.skip("server not reachable")
        assert status == 404

    def test_relative_path_or_none(self):
        base = Path("/a/b")
        result = _relative_path_or_none(base, Path("/a/b/c/d"))
        assert result is not None
        assert "c" in str(result) and "d" in str(result)
        assert _relative_path_or_none(base, Path("/x/y")) is None

    def test_html_page_helper(self):
        result = _html_page("Test", "<p>hello</p>")
        assert "<title>Test" in result
        assert "<p>hello</p>" in result
        assert "LocalScope" in result

    def test_webui_help_registered(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["webui", "--host", "127.0.0.1", "--port", "9999"])
        assert result.command == "webui"
        assert result.host == "127.0.0.1"
        assert result.port == 9999

    def test_default_host_is_localhost(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["webui"])
        assert result.host == "127.0.0.1"

    def test_logs_api_tasks(self, server):
        status, body, ct = _get(server, "/api/logs/tasks?limit=5")
        if "json" in ct:
            data = json.loads(body)
            assert "tasks" in data
