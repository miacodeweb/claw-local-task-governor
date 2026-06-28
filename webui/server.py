"""LocalScope Web UI — minimal read-only dashboard for reports, logs, benchmarks.

Uses only Python stdlib (no external dependencies).
Runs on 127.0.0.1 by default — never binds to 0.0.0.0 unless explicitly requested.
"""

from __future__ import annotations

import json
import re
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from governor.logging_manager import read_log_errors, read_log_summary, read_log_tasks
from governor.model_recommendations import get_model_recommendations

REPORTS_DIR = Path("reports")
BENCHMARKS_DIR = REPORTS_DIR / "benchmarks"
LOGS_DIR = Path("logs")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSS = """
body{font-family:system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:20px;background:#0d1117;color:#c9d1d9}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
h1,h2{border-bottom:1px solid #30363d;padding-bottom:8px}
table{width:100%;border-collapse:collapse;margin:10px 0}
th,td{border:1px solid #30363d;padding:8px;text-align:left}
th{background:#161b22}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px;margin:10px 0}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600}
.bg-ok{background:#23863633;color:#3fb950}.bg-warn{background:#9e6a0333;color:#d29922}
.bg-err{background:#da363333;color:#f85149}.bg-info{background:#1f6feb33;color:#58a6ff}
nav{margin:10px 0 20px}nav a{margin-right:16px}
pre{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;overflow-x:auto;font-size:13px}
footer{margin-top:40px;padding-top:20px;border-top:1px solid #30363d;font-size:12px;color:#8b949e}
""".replace("\n", "")


def _html_page(title: str, body: str, nav_links: list[tuple[str, str]] | None = None) -> str:
    nav = ""
    if nav_links:
        links = "".join(f'<a href="{href}">{label}</a>' for label, href in nav_links)
        nav = f"<nav>{links}</nav>"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{title} – LocalScope</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head><body>
<h1>LocalScope</h1>{nav}{body}<footer>LocalScope 0.1.0 &mdash; Read-only Web UI &mdash; local only</footer>
</body></html>"""


NAV_LINKS: list[tuple[str, str]] = [
    ("Dashboard", "/"),
    ("Reports", "/reports"),
    ("Logs", "/logs"),
    ("Benchmarks", "/benchmarks"),
    ("Models", "/models/recommendations"),
]


def _relative_path_or_none(base: Path, target: Path) -> str | None:
    try:
        rel = target.resolve().relative_to(base.resolve())
        return str(rel)
    except ValueError:
        return None


class LocalScopeHandler(BaseHTTPRequestHandler):
    """Read-only HTTP handler for LocalScope artifacts."""

    server_version = "LocalScope-WebUI/0.1"

    def log_message(self, format, *args):
        return

    def _send_html(self, code: int, content: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, code: int, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode("utf-8"))

    def _send_error_msg(self, code: int, msg: str):
        self._send_html(code, _html_page("Error", f"<div class='card'><h2>{code}</h2><p>{msg}</p></div>"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path in ("/", "/dashboard"):
            return self._dashboard()
        if path == "/api/status":
            return self._api_status()
        if path == "/reports":
            return self._reports_list()
        if path.startswith("/reports/") and len(path) > 9:
            return self._report_detail(path[9:])
        if path == "/api/reports":
            return self._api_reports()
        if path.startswith("/api/reports/") and len(path) > 13:
            return self._api_report_detail(path[13:])
        if path in ("/logs", "/logs/errors", "/logs/tasks"):
            return self._logs_view(path)
        if path == "/api/logs/errors":
            return self._api_logs_errors(qs)
        if path == "/api/logs/tasks":
            return self._api_logs_tasks(qs)
        if path == "/benchmarks":
            return self._benchmarks_list()
        if path.startswith("/benchmarks/") and len(path) > 12:
            return self._benchmark_detail(path[12:])
        if path == "/api/benchmarks":
            return self._api_benchmarks()
        if path in ("/models/recommendations", "/model-recommendations"):
            return self._model_recommendations_view()
        if path == "/api/model-recommendations":
            return self._api_model_recommendations(qs)
        if path == "/graphify":
            return self._graphify_view()
        if path == "/api/graphify":
            return self._api_graphify()

        self._send_error_msg(404, f"Not found: {path}")

    # ── Dashboard ──────────────────────────────────────

    def _dashboard(self):
        report_count = len(list(REPORTS_DIR.glob("audit-*.json"))) if REPORTS_DIR.is_dir() else 0
        bench_count = len(list(BENCHMARKS_DIR.glob("*.json"))) if BENCHMARKS_DIR.is_dir() else 0
        log_summary = read_log_summary(LOGS_DIR) if LOGS_DIR.is_dir() else {"runs": 0, "tasks": 0, "errors": 0}
        error_count = log_summary.get("errors", 0)
        rec = get_model_recommendations(latest_benchmark=True)

        body = f"""<div class="card"><h2>Dashboard</h2>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Reports</td><td>{report_count}</td></tr>
<tr><td>Benchmarks</td><td>{bench_count}</td></tr>
<tr><td>Log errors</td><td>{error_count}</td></tr>
<tr><td>Log tasks</td><td>{log_summary.get('tasks', 0)}</td></tr>
<tr><td>Last recommended model</td><td>{rec.model} <span class="badge bg-info">{rec.confidence}</span></td></tr>
</table></div>"""
        self._send_html(200, _html_page("Dashboard", body, NAV_LINKS))

    def _api_status(self):
        rec = get_model_recommendations(latest_benchmark=True)
        log_summary = read_log_summary(LOGS_DIR) if LOGS_DIR.is_dir() else {}
        report_count = len(list(REPORTS_DIR.glob("audit-*.json"))) if REPORTS_DIR.is_dir() else 0
        bench_count = len(list(BENCHMARKS_DIR.glob("*.json"))) if BENCHMARKS_DIR.is_dir() else 0
        self._send_json(200, {
            "name": "LocalScope",
            "version": "0.1.0",
            "reports": report_count,
            "benchmarks": bench_count,
            "log_runs": log_summary.get("runs", 0),
            "log_tasks": log_summary.get("tasks", 0),
            "log_errors": log_summary.get("errors", 0),
            "recommended_model": rec.to_dict(),
        })

    # ── Reports ────────────────────────────────────────

    def _reports_list(self):
        items = self._list_report_files()
        rows = ""
        for r in items:
            rows += f"<tr><td><a href='/reports/{r['id']}'>{r['file']}</a></td><td>{r['model']}</td><td>{r['profile']}</td><td>{r['tasks']}</td><td>{r['date']}</td></tr>"
        body = f"""<div class="card"><h2>Reports</h2>
<table><tr><th>File</th><th>Model</th><th>Profile</th><th>Tasks</th><th>Date</th></tr>
{rows or '<tr><td colspan=5>No reports found.</td></tr>'}</table></div>"""
        self._send_html(200, _html_page("Reports", body, NAV_LINKS))

    def _report_detail(self, report_id: str):
        data = self._load_report_json(report_id)
        if data is None:
            return self._send_error_msg(404, f"Report not found: {report_id}")
        meta = data.get("metadata", {})
        counts = data.get("counts", data.get("totals", {}))
        summary = data.get("summary", "")
        body = f"""<div class="card"><h2>Report: {report_id}</h2>
<table><tr><th>Field</th><th>Value</th></tr>
<tr><td>Project</td><td>{meta.get('project_path', '')}</td></tr>
<tr><td>Generated</td><td>{meta.get('generated_at', '')}</td></tr>
<tr><td>Profile</td><td>{meta.get('profile_detected', '')}</td></tr>
<tr><td>Model</td><td>{meta.get('model_used', '')}</td></tr>
<tr><td>Tasks processed</td><td>{counts.get('tasks_processed', 0)}</td></tr>
<tr><td>JSON valid</td><td>{counts.get('json_valid', 0)}</td></tr>
<tr><td>JSON repaired</td><td>{counts.get('json_repaired', 0)}</td></tr>
<tr><td>JSON failed</td><td>{counts.get('json_failed', 0)}</td></tr>
</table>
<p><strong>Summary:</strong> {summary}</p></div>"""
        self._send_html(200, _html_page(f"Report – {report_id}", body, NAV_LINKS))

    def _api_reports(self):
        self._send_json(200, self._list_report_files())

    def _api_report_detail(self, report_id: str):
        data = self._load_report_json(report_id)
        if data is None:
            return self._send_json(404, {"error": "report not found", "id": report_id})
        self._send_json(200, data)

    def _list_report_files(self) -> list[dict]:
        items = []
        if not REPORTS_DIR.is_dir():
            return items
        for f in sorted(REPORTS_DIR.glob("audit-*.json"), reverse=True)[:50]:
            data = self._load_report_json(f.name)
            meta = (data or {}).get("metadata", {})
            counts = (data or {}).get("counts", (data or {}).get("totals", {}))
            items.append({
                "id": f.stem,
                "file": f.name,
                "model": meta.get("model_used", ""),
                "profile": meta.get("profile_detected", ""),
                "tasks": counts.get("tasks_processed", 0),
                "date": meta.get("generated_at", ""),
            })
        return items

    def _load_report_json(self, name: str) -> dict | None:
        path = REPORTS_DIR / name
        if path.name not in str(name) or ".." in name or "/" in name or "\\" in name:
            return None
        if not path.is_file():
            return None
        rel = _relative_path_or_none(PROJECT_ROOT, path)
        if rel is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # ── Logs ───────────────────────────────────────────

    def _logs_view(self, path: str):
        if path == "/logs":
            summary = read_log_summary(LOGS_DIR) if LOGS_DIR.is_dir() else {}
            body = f"""<div class="card"><h2>Logs</h2>
<table><tr><th>Type</th><th>Count</th><th></th></tr>
<tr><td>Runs</td><td>{summary.get('runs', 0)}</td><td></td></tr>
<tr><td>Tasks</td><td>{summary.get('tasks', 0)}</td><td><a href='/logs/tasks'>view</a></td></tr>
<tr><td>Errors</td><td>{summary.get('errors', 0)}</td><td><a href='/logs/errors'>view</a></td></tr>
</table></div>"""
        elif path == "/logs/errors":
            entries = read_log_errors(LOGS_DIR, limit=50) if LOGS_DIR.is_dir() else []
            rows = ""
            for e in entries:
                rows += f"<tr><td>{e.get('timestamp', '')}</td><td><span class='badge bg-err'>{e.get('error_type', '')}</span></td><td>{e.get('error_message', '')[:120]}</td><td>{e.get('task_id', '')}</td></tr>"
            body = f"""<div class="card"><h2>Error Logs</h2>
<table><tr><th>Time</th><th>Type</th><th>Message</th><th>Task</th></tr>
{rows or '<tr><td colspan=4>No errors.</td></tr>'}</table></div>"""
        elif path == "/logs/tasks":
            entries = read_log_tasks(LOGS_DIR, limit=50) if LOGS_DIR.is_dir() else []
            rows = ""
            for e in entries:
                badge = "bg-ok" if e.get("json_valid") else ("bg-warn" if e.get("json_repaired") else "bg-err")
                rows += f"<tr><td>{e.get('timestamp', '')}</td><td>{e.get('event', '')}</td><td>{e.get('task_id', '')}</td><td>{e.get('file_path', '')}</td><td><span class='badge {badge}'>{'valid' if e.get('json_valid') else ('repaired' if e.get('json_repaired') else 'failed')}</span></td></tr>"
            body = f"""<div class="card"><h2>Task Logs</h2>
<table><tr><th>Time</th><th>Event</th><th>Task</th><th>File</th><th>JSON</th></tr>
{rows or '<tr><td colspan=5>No tasks.</td></tr>'}</table></div>"""
        else:
            body = ""
        self._send_html(200, _html_page("Logs", body, NAV_LINKS))

    def _api_logs_errors(self, qs):
        limit = int(qs.get("limit", [20])[0])
        entries = read_log_errors(LOGS_DIR, limit=min(limit, 200)) if LOGS_DIR.is_dir() else []
        self._send_json(200, {"errors": entries, "count": len(entries)})

    def _api_logs_tasks(self, qs):
        limit = int(qs.get("limit", [20])[0])
        entries = read_log_tasks(LOGS_DIR, limit=min(limit, 200)) if LOGS_DIR.is_dir() else []
        self._send_json(200, {"tasks": entries, "count": len(entries)})

    # ── Benchmarks ─────────────────────────────────────

    def _benchmarks_list(self):
        items = self._list_benchmark_files()
        rows = ""
        for b in items:
            rows += f"<tr><td><a href='/benchmarks/{b['id']}'>{b['file']}</a></td><td>{b['type']}</td><td>{b['models']}</td><td>{b['best']}</td></tr>"
        body = f"""<div class="card"><h2>Benchmarks</h2>
<table><tr><th>File</th><th>Type</th><th>Models</th><th>Best</th></tr>
{rows or '<tr><td colspan=4>No benchmarks found.</td></tr>'}</table></div>"""
        self._send_html(200, _html_page("Benchmarks", body, NAV_LINKS))

    def _benchmark_detail(self, bench_id: str):
        data = self._load_benchmark_json(bench_id)
        if data is None:
            return self._send_error_msg(404, f"Benchmark not found: {bench_id}")
        summary = data.get("summary", {})
        models_data = data.get("models", [])
        profiles = data.get("profiles", {})
        rows = ""
        if profiles:
            for pname, pdata in profiles.items():
                rows += f"<tr><td>{pname}</td><td>{pdata.get('best_overall_model', '')}</td><td>{pdata.get('best_json_model', '')}</td><td>{pdata.get('fastest_model', '')}</td></tr>"
        else:
            for m in models_data:
                rows += f"<tr><td>{m.get('model', '')}</td><td>{m.get('overall_score', 0):.4f}</td><td>{m.get('json_valid_rate', 0):.2f}</td><td>{m.get('average_response_ms', 0):.0f}ms</td></tr>"
        best = summary.get("best_overall_model") or (profiles and "see table" or "N/A")
        body = f"""<div class="card"><h2>Benchmark: {bench_id}</h2>
<p><strong>Best overall:</strong> {best}</p>
<p><strong>Best JSON:</strong> {summary.get('best_json_model', 'N/A')}</p>
<p><strong>Fastest:</strong> {summary.get('fastest_model', 'N/A')}</p>
<table><tr><th>{'Profile' if profiles else 'Model'}</th><th>{'Best Overall' if profiles else 'Score'}</th><th>{'Best JSON' if profiles else 'JSON Rate'}</th><th>{'Fastest' if profiles else 'Avg ms'}</th></tr>
{rows}</table></div>"""
        self._send_html(200, _html_page(f"Benchmark – {bench_id}", body, NAV_LINKS))

    def _api_benchmarks(self):
        self._send_json(200, self._list_benchmark_files())

    def _list_benchmark_files(self) -> list[dict]:
        items = []
        if not BENCHMARKS_DIR.is_dir():
            return items
        for f in sorted(BENCHMARKS_DIR.glob("*.json"), reverse=True)[:50]:
            data = self._load_benchmark_json(f.name)
            bench_type = "profile" if f.stem.startswith("profile-") else "model"
            models = data.get("metadata", {}).get("models", []) if data else []
            summary = (data or {}).get("summary", {})
            items.append({
                "id": f.stem,
                "file": f.name,
                "type": bench_type,
                "models": ", ".join(models[:3]),
                "best": summary.get("best_overall_model", ""),
            })
        return items

    def _load_benchmark_json(self, name: str) -> dict | None:
        path = BENCHMARKS_DIR / name
        if ".." in name or "/" in name or "\\" in name:
            return None
        if not path.is_file():
            return None
        rel = _relative_path_or_none(PROJECT_ROOT, path)
        if rel is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # ── Models ─────────────────────────────────────────

    def _model_recommendations_view(self):
        rec = get_model_recommendations(latest_benchmark=True)
        w = "".join(f"<li>{w}</li>" for w in rec.warnings) or "<li>None</li>"
        body = f"""<div class="card"><h2>Model Recommendations</h2>
<table><tr><th>Field</th><th>Value</th></tr>
<tr><td>Recommended model</td><td><strong>{rec.model}</strong></td></tr>
<tr><td>Prompt version</td><td>{rec.prompt_version}</td></tr>
<tr><td>Max chars</td><td>{rec.max_chars}</td></tr>
<tr><td>Source</td><td>{rec.source}</td></tr>
<tr><td>Confidence</td><td><span class="badge {'bg-ok' if rec.confidence=='high' else ('bg-warn' if rec.confidence=='medium' else 'bg-err')}">{rec.confidence}</span></td></tr>
<tr><td>Best JSON model</td><td>{rec.best_json_model or 'N/A'}</td></tr>
<tr><td>Fastest model</td><td>{rec.fastest_model or 'N/A'}</td></tr>
<tr><td>Most stable model</td><td>{rec.most_stable_model or 'N/A'}</td></tr>
</table>
<h3>Warnings</h3><ul>{w}</ul>
<p><em>Suggestion: {rec.suggestion or 'None'}</em></p></div>"""
        self._send_html(200, _html_page("Model Recommendations", body, NAV_LINKS))

    def _api_model_recommendations(self, qs):
        profile = qs.get("profile", ["general"])[0]
        task_type = qs.get("task_type", [None])[0]
        rec = get_model_recommendations(profile=profile, task_type=task_type, latest_benchmark=True)
        self._send_json(200, rec.to_dict())

    # ── Graphify ───────────────────────────────────────

    def _graphify_view(self):
        try:
            from governor.graphify_adapter import get_graph_summary
            summary = get_graph_summary(Path("."))
        except Exception:
            summary = {"available": False}
        if summary.get("available"):
            body = f"""<div class="card"><h2>Graphify</h2>
<p><span class="badge bg-ok">Detected</span></p>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Nodes</td><td>{summary.get('nodes_detected', 0)}</td></tr>
<tr><td>Edges</td><td>{summary.get('edges_detected', 0)}</td></tr>
<tr><td>Referenced files</td><td>{len(summary.get('referenced_files', []))}</td></tr>
<tr><td>Central nodes</td><td>{len(summary.get('central_nodes', []))}</td></tr>
</table></div>"""
        else:
            body = """<div class="card"><h2>Graphify</h2><p><span class="badge bg-warn">Not detected</span></p><p>Graphify is optional. Run <code>graphify</code> on a project to use it.</p></div>"""
        self._send_html(200, _html_page("Graphify", body, NAV_LINKS))

    def _api_graphify(self):
        try:
            from governor.graphify_adapter import get_graph_summary
            summary = get_graph_summary(Path("."))
        except Exception as e:
            summary = {"available": False, "error": str(e)}
        self._send_json(200, summary)


def run_webui(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    print(f"LocalScope Web UI starting at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server = HTTPServer((host, port), LocalScopeHandler)
    if open_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web UI.")
        server.server_close()
