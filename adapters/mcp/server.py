"""Experimental minimal MCP stdio server for LocalScope.

This module intentionally exposes a small high-level, read-only tool surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.common.audit_request import AuditRequest  # noqa: E402
from adapters.common.audit_response import AuditResponse  # noqa: E402
from adapters.common.run_audit import run_audit  # noqa: E402
from governor.graphify_adapter import get_graph_summary  # noqa: E402
from governor.openclaw_tool import local_audit_report, local_audit_status  # noqa: E402
from governor.safety import (  # noqa: E402
    FORBIDDEN_TOOL_NAMES,
    MAX_TASKS_LIMIT,
    STATUS_LIMIT_DEFAULT,
    STATUS_LIMIT_MAX,
    validate_max_tasks,
    validate_mcp_tool_names,
    validate_project_path,
    validate_read_only,
    validate_report_path as safety_validate_report_path,
)


AUDIT_TOOL = "localscope_audit"
STATUS_TOOL = "localscope_status"
REPORT_TOOL = "localscope_report"
GRAPH_INFO_TOOL = "localscope_graph_info"
TOOL_NAMES = {AUDIT_TOOL, STATUS_TOOL, REPORT_TOOL, GRAPH_INFO_TOOL}
LOCAL_REPORTS_DIR = PROJECT_ROOT / "reports"
AUDIT_ALLOWED_ARGUMENTS = {
    "path",
    "profile",
    "mode",
    "max_tasks",
    "use_memory",
    "use_graphify",
    "read_only",
}
FORBIDDEN_ARGUMENTS = {
    "write",
    "write_file",
    "edit",
    "apply_patch",
    "patch",
    "run_command",
    "command",
    "shell",
    "exec",
    "output_dir",
}


def list_tools() -> list[dict[str, Any]]:
    """Return the MCP tools exposed by this server."""
    tools = [
        {
            "name": AUDIT_TOOL,
            "description": "Run a read-only LocalScope audit over one local project folder.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "profile": {
                        "type": "string",
                        "enum": [
                            "auto",
                            "general",
                            "php",
                            "wordpress",
                            "javascript",
                            "python",
                            "java",
                            "docker",
                            "config_files",
                            "windows_folder",
                            "linux_folder",
                            "documentation",
                        ],
                        "default": "auto",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["general", "security", "code_quality", "config_audit"],
                        "default": "general",
                    },
                    "max_tasks": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TASKS_LIMIT,
                        "default": 5,
                    },
                    "use_memory": {"type": "boolean", "default": True},
                    "use_graphify": {"type": "boolean", "default": True},
                    "read_only": {"type": "boolean", "const": True, "default": True},
                },
                "required": ["path"],
            },
        },
        {
            "name": STATUS_TOOL,
            "description": "Return recent LocalScope audit status without running analysis.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": STATUS_LIMIT_MAX,
                        "default": STATUS_LIMIT_DEFAULT,
                    }
                },
            },
        },
        {
            "name": REPORT_TOOL,
            "description": "Read a LocalScope audit report summary from reports/audit-*.json or .md.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"report_path": {"type": "string", "minLength": 1}},
                "required": ["report_path"],
            },
        },
        {
            "name": GRAPH_INFO_TOOL,
            "description": "Return optional Graphify diagnostics for one project folder without running Graphify.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"path": {"type": "string", "minLength": 1}},
                "required": ["path"],
            },
        },
    ]
    validate_mcp_tool_names({tool["name"] for tool in tools})
    return tools


def localscope_audit(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run LocalScope through the common adapter contract and return JSON-safe data."""
    args = dict(arguments or {})
    validation_error = validate_audit_arguments(args)
    if validation_error:
        return validation_error.to_dict()

    try:
        request = AuditRequest.from_dict(args)
    except (TypeError, ValueError) as error:
        return AuditResponse.failed(adapter="mcp", project_path=str(args.get("path", "")), summary=str(error)).to_dict()

    return run_audit(request, adapter="mcp").to_dict()


def localscope_status(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return recent audit status without scanning or running model analysis."""
    args = dict(arguments or {})
    unexpected = sorted(set(args) - {"limit"})
    if unexpected:
        return query_error(f"unsupported arguments: {', '.join(unexpected)}")

    try:
        limit = int(args.get("limit", STATUS_LIMIT_DEFAULT))
    except (TypeError, ValueError):
        return query_error("limit must be an integer")
    if limit < 1:
        return query_error("limit must be greater than 0")
    if limit > STATUS_LIMIT_MAX:
        return query_error(f"limit must be less than or equal to {STATUS_LIMIT_MAX}")

    try:
        status = local_audit_status(output_dir=LOCAL_REPORTS_DIR, limit=limit)
    except Exception as error:  # noqa: BLE001 - MCP query must return structured errors.
        return query_error(str(error))

    status["adapter"] = "mcp"
    status["memory"] = {
        "path": str((PROJECT_ROOT / "data" / "memory.sqlite").resolve()),
        "exists": (PROJECT_ROOT / "data" / "memory.sqlite").exists(),
    }
    return status


def localscope_report(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Return a structured summary for a LocalScope report."""
    args = dict(arguments or {})
    unexpected = sorted(set(args) - {"report_path"})
    if unexpected:
        return query_error(f"unsupported arguments: {', '.join(unexpected)}")

    report_path = str(args.get("report_path", "")).strip()
    if not report_path:
        return query_error("report_path is required")

    allowed, error = validate_report_path(Path(report_path))
    if not allowed:
        return query_error(error or "report_path is not allowed")

    try:
        report = local_audit_report(report_path=report_path)
    except Exception as error:  # noqa: BLE001 - MCP query must return structured errors.
        return query_error(str(error))

    report["adapter"] = "mcp"
    return report


def localscope_graph_info(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Return optional Graphify diagnostics without running Graphify."""
    args = dict(arguments or {})
    unexpected = sorted(set(args) - {"path"})
    if unexpected:
        return query_error(f"unsupported arguments: {', '.join(unexpected)}")

    path_value = str(args.get("path", "")).strip()
    try:
        project_path = validate_project_path(path_value)
    except ValueError as error:
        return query_error(str(error), project_path=path_value)

    try:
        summary = get_graph_summary(project_path)
    except Exception as error:  # noqa: BLE001 - MCP query must return structured errors.
        return query_error(str(error), project_path=path_value)

    return {
        "status": "completed",
        "adapter": "mcp",
        "project_path": str(project_path.resolve()),
        "available": bool(summary.get("available")),
        "graph_path": summary.get("graph_path") or "",
        "nodes_count": int(summary.get("nodes_count", 0)),
        "edges_count": int(summary.get("edges_count", 0)),
        "important_files": list(summary.get("important_files", [])),
        "warnings": [str(warning) for warning in summary.get("warnings", [])],
    }


def validate_audit_arguments(args: dict[str, Any]) -> AuditResponse | None:
    """Validate MCP arguments before running the audit flow."""
    unexpected = sorted(set(args) - AUDIT_ALLOWED_ARGUMENTS)
    forbidden = sorted((set(args) & FORBIDDEN_ARGUMENTS) | (set(args) & FORBIDDEN_TOOL_NAMES))
    if unexpected or forbidden:
        details = []
        if unexpected:
            details.append(f"unsupported arguments: {', '.join(unexpected)}")
        if forbidden:
            details.append(f"forbidden write or command arguments: {', '.join(forbidden)}")
        summary = "; ".join(details)
        return AuditResponse.failed(adapter="mcp", project_path=str(args.get("path", "")), summary=summary)

    path_value = str(args.get("path", "")).strip()
    try:
        validate_read_only(args.get("read_only", True))
    except ValueError:
        return AuditResponse.failed(
            adapter="mcp",
            project_path=path_value,
            summary="read_only must be true; editing is not supported",
            errors=["read_only=false rejected"],
        )

    try:
        validate_max_tasks(args.get("max_tasks", 5))
    except ValueError as error:
        return AuditResponse.failed(adapter="mcp", project_path=path_value, summary=str(error))

    try:
        validate_project_path(path_value)
    except ValueError as error:
        return AuditResponse.failed(adapter="mcp", project_path=path_value, summary=str(error))

    return None


def validate_report_path(report_path: Path) -> tuple[bool, str]:
    """Allow only LocalScope-owned reports/audit-* markdown or JSON files."""
    try:
        safety_validate_report_path(report_path, reports_root=LOCAL_REPORTS_DIR)
    except ValueError as error:
        return False, str(error)
    return True, ""


def query_error(summary: str, *, project_path: str = "") -> dict[str, Any]:
    return {
        "status": "failed",
        "adapter": "mcp",
        "project_path": project_path,
        "summary": summary,
        "errors": [summary],
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC MCP message."""
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return rpc_result(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "localscope-mcp", "version": "0.1.0"},
            },
        )

    if method == "tools/list":
        return rpc_result(message_id, {"tools": list_tools()})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == AUDIT_TOOL:
            data = localscope_audit(arguments)
        elif name == STATUS_TOOL:
            data = localscope_status(arguments)
        elif name == REPORT_TOOL:
            data = localscope_report(arguments)
        elif name == GRAPH_INFO_TOOL:
            data = localscope_graph_info(arguments)
        else:
            data = AuditResponse.failed(
                adapter="mcp",
                summary=f"unknown tool: {name}",
                errors=[f"unknown tool: {name}"],
            ).to_dict()
        return rpc_result(
            message_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(data, ensure_ascii=False),
                    }
                ],
                "isError": data.get("status") == "failed",
            },
        )

    return rpc_error(message_id, code=-32601, message=f"method not found: {method}")


def rpc_result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def rpc_error(message_id: Any, *, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout, error_stream: TextIO = sys.stderr) -> int:
    """Run a line-delimited JSON-RPC stdio server."""
    for line in input_stream:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle_request(message)
        except Exception as error:  # noqa: BLE001 - MCP transport must stay alive.
            print(f"LocalScope MCP error: {error}", file=error_stream)
            response = rpc_error(None, code=-32700, message=str(error))

        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False))
            output_stream.write("\n")
            output_stream.flush()
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
