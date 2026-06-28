# LocalScope OpenCode Adapter

This adapter lets OpenCode use LocalScope as one high-level external tool.

CLI wrapper tool:

```text
local_scope_audit
```

MCP tool:

```text
localscope_audit
```

It runs the LocalScope flow:

```text
scan -> tasks -> run-tasks -> report
```

The adapter is read-only and does not expose small file, shell, or patch tools.

## Manual Test

From the repository root:

```powershell
python -m adapters.opencode.local_scope_audit --path "D:\ruta\al\proyecto" --profile auto --mode general --max-tasks 5 --read-only true
```

The command writes JSON only to stdout so OpenCode can parse it directly.

## Using LocalScope MCP With OpenCode

OpenCode can also use LocalScope through the experimental MCP server. MCP is the preferred direction for agent integration because LocalScope exposes a few high-level tools instead of many small tools. That keeps local models focused and avoids saturating them with filesystem, shell, or editing schemas.

Detailed setup guide:

```text
adapters/opencode/MCP_SETUP.md
```

Start the server from the repository root:

```powershell
cd D:\claw-local-task-governor
python -m adapters.mcp.server
```

Conceptual OpenCode MCP configuration:

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

Available MCP tools:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
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

Example MCP call:

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

LocalScope MCP does not expose:

```text
read_file
write_file
run_command
apply_patch
shell
exec
```

Graphify remains separate. Graphify can generate `graphify-out/graph.json`; LocalScope can consume that file as optional context when `use_graphify` is `true`. LocalScope MCP does not replace a Graphify MCP server.

## External Tool Shape

Configure OpenCode to call the wrapper with these arguments:

```json
{
  "path": "D:/path/to/project",
  "profile": "auto",
  "mode": "general",
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
  "adapter": "opencode",
  "project_path": "D:/path/to/project",
  "profile_detected": "python",
  "report_markdown": "reports/audit.md",
  "report_json": "reports/audit.json",
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

- `read_only` must be `true`.
- `read_only=false` is rejected with a JSON failure response.
- The adapter does not expose `read_file`, `write_file`, `run_command`, or `apply_patch`.
- The audited project is not edited.
- LocalScope writes only its own outputs under `reports/` and `data/`.

## MCP Troubleshooting

| Problem | What to check |
| --- | --- |
| MCP server no inicia | Run `python -m adapters.mcp.server` manually from `D:\claw-local-task-governor`. |
| Python path incorrecto | Use the same Python or virtual environment that runs `pytest`; set OpenCode `cwd` to the repository root. |
| Windows path con espacios | Quote paths or use forward slashes, for example `D:/Mis Proyectos/App Demo`. |
| Ollama apagado | Run `ollama list`, `ollama serve`, and `python -m governor.main ollama-test`. |
| JSON/logs mezclados | The MCP server must write JSON only to stdout; debug output belongs on stderr. |
| OpenCode no ve la tool | Confirm the MCP config command is `python -m adapters.mcp.server` and verify that `tools/list` returns `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`. |

## Current Limits

- CLI wrapper is stable; MCP server is experimental.
- MCP exposes `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`.
- The status, report, and graph tools are read-only queries and do not run a new audit.
- Graphify is optional and only consumed if existing output is present.
- The final report is deterministic and not model-written in this MVP.
