# LocalScope MCP Adapter

This is the first experimental MCP adapter for LocalScope.

Current scope: one high-level audit tool plus three read-only query tools.

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

`localscope_audit` runs the existing LocalScope flow through the shared adapter contract:

```text
scan -> tasks -> run-tasks -> report
```

The status, report, and graph tools only read existing LocalScope/Graphify outputs.

It does not expose generic filesystem, shell, write, patch, or low-level file tools.

## Dependency Decision

No external MCP Python package is required in this MVP step. The environment does not include an `mcp` package, and LocalScope currently has no runtime dependencies.

`adapters/mcp/server.py` implements a small line-delimited JSON-RPC stdio server for the minimal MCP methods needed by compatible clients:

- `initialize`
- `tools/list`
- `tools/call`

This keeps the adapter lightweight and avoids adding a dependency before the integration shape is proven.

## Tools

### localscope_audit

Runs a read-only audit.

```json
{
  "path": "string",
  "profile": "auto",
  "mode": "general",
  "max_tasks": 5,
  "use_memory": true,
  "use_graphify": true,
  "read_only": true
}
```

Supported profiles:

```text
auto, general, php, wordpress, javascript, python, java, docker, config_files, windows_folder, linux_folder, documentation
```

Supported modes:

```text
general, security, code_quality, config_audit
```

`read_only` must be `true`. `max_tasks` must be between `1` and `100`.

### localscope_status

Returns recent LocalScope report status without running a new audit.

```json
{
  "limit": 5
}
```

It reads LocalScope-owned outputs under `reports/` and reports basic memory file status.

### localscope_report

Reads a LocalScope-generated report summary.

```json
{
  "report_path": "D:/claw-local-task-governor/reports/audit-YYYYMMDD-HHMMSS.json"
}
```

Allowed report paths must point to `reports/audit-*.json` or `reports/audit-*.md` inside the LocalScope repository reports folder.

### localscope_graph_info

Returns optional Graphify diagnostics without running Graphify.

```json
{
  "path": "D:/ruta/al/proyecto"
}
```

Response includes:

```json
{
  "available": true,
  "graph_path": "string",
  "nodes_count": 0,
  "edges_count": 0,
  "important_files": [],
  "warnings": []
}
```

## Start Server

From the repository root:

```powershell
python -m adapters.mcp.server
```

The server writes protocol responses to stdout. Human/debug errors go to stderr.

## Using LocalScope MCP With OpenCode

LocalScope MCP is meant to give OpenCode one small, high-level audit surface instead of many small tools. This helps local models because they see one controlled tool schema, not a broad filesystem or shell toolbox.

Start the MCP server from the repository root:

```powershell
cd D:\claw-local-task-governor
python -m adapters.mcp.server
```

Available tools:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

No low-level MCP tools are implemented.

### Conceptual OpenCode Configuration

Exact configuration depends on the OpenCode MCP configuration format in use, but the shape should be equivalent to:

```json
{
  "mcpServers": {
    "localscope": {
      "command": "python",
      "args": ["-m", "adapters.mcp.server"],
      "cwd": "D:/claw-local-task-governor"
    }
  }
}
```

If the path contains spaces, keep the `cwd` value quoted in the OpenCode configuration format used by your environment.

### Example Tool Calls

Call `localscope_audit` with:

```json
{
  "path": "D:/ruta/al/proyecto",
  "profile": "auto",
  "mode": "general",
  "max_tasks": 5,
  "use_memory": true,
  "use_graphify": true,
  "read_only": true
}
```

Call `localscope_status` with:

```json
{
  "limit": 5
}
```

Call `localscope_report` with:

```json
{
  "report_path": "D:/claw-local-task-governor/reports/audit-YYYYMMDD-HHMMSS.json"
}
```

Call `localscope_graph_info` with:

```json
{
  "path": "D:/ruta/al/proyecto"
}
```

Supported arguments:

```json
{
  "path": "string",
  "profile": "auto|general|php|wordpress|javascript|python|java|docker|windows_folder|linux_folder",
  "mode": "general|security|code_quality|config_audit",
  "max_tasks": 5,
  "use_memory": true,
  "use_graphify": true,
  "read_only": true
}
```

Expected response:

```json
{
  "status": "completed",
  "adapter": "mcp",
  "project_path": "D:/ruta/al/proyecto",
  "profile_detected": "python",
  "report_markdown": "reports/audit-YYYYMMDD-HHMMSS.md",
  "report_json": "reports/audit-YYYYMMDD-HHMMSS.json",
  "tasks_processed": 5,
  "reused": 0,
  "json_valid": 5,
  "json_repaired": 0,
  "json_failed": 0,
  "summary": "Audit completed.",
  "errors": []
}
```

## Safety

- Only high-level LocalScope tools are registered.
- Query tools are read-only and do not trigger new analysis.
- `read_only=false` is rejected.
- Empty or missing paths are rejected.
- Missing paths are rejected.
- Filesystem roots are rejected as audit targets.
- Quoted Windows paths and paths with spaces are normalized before validation.
- Excessive `max_tasks` values are rejected.
- Unsupported arguments are rejected.
- Write/command arguments such as `write_file`, `run_command`, `shell`, `exec`, and `apply_patch` are rejected.
- Graphify remains optional and is only read if existing output is present.

LocalScope MCP does not expose:

```text
read_file
write_file
run_command
apply_patch
shell
exec
```

## Graphify Relationship

Graphify can still generate a project knowledge graph separately:

```text
graphify-out/graph.json
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
```

If these files exist, LocalScope can consume them as optional context for prioritization and reporting. LocalScope MCP does not run Graphify automatically and does not try to replace a future Graphify MCP server. The roles stay separate:

- Graphify: graph generation and structural project knowledge.
- LocalScope MCP: audit orchestration, JSON Guard validation, SQLite memory reuse, Graphify context consumption, and reports.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| MCP server no inicia | Run `python -m adapters.mcp.server` from the repository root and confirm Python can import `adapters`. |
| Python path incorrecto | Set OpenCode `cwd` to `D:/claw-local-task-governor`, or use the Python interpreter from the project virtual environment. |
| Windows path con espacios | Quote paths in the OpenCode config and in tool calls, for example `D:/Mis Proyectos/App Demo`. |
| Ollama apagado | Run `ollama list`, then `ollama serve`, then test `python -m governor.main ollama-test`. MCP returns structured errors instead of logs in stdout. |
| JSON/logs mezclados | Keep human logs on stderr only. The MCP server writes protocol JSON to stdout. Avoid adding `print()` debugging to stdout. |
| OpenCode no ve la tool | Confirm OpenCode is launching `python -m adapters.mcp.server`, then inspect `tools/list`; it should show `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`. |
| Graphify no detectado | Run `python -m governor.main graphify-info <path>` and confirm `graphify-out/graph.json` exists if Graphify context is expected. |

## Current Limits

- Experimental stdio server, not a full dependency-backed MCP implementation.
- Long audits are synchronous.
- Concurrent calls should use separate output directories in a future version; this minimal tool currently uses the default LocalScope `reports/` output path.
- `localscope_report` only reads LocalScope-owned `reports/audit-*` files.
- `max_tasks` is capped at `100`.
