# LocalScope MCP Setup For OpenCode

This guide explains how to connect OpenCode to LocalScope through the experimental MCP stdio server.

LocalScope exposes a small set of high-level read-only tools so OpenCode can request audits and summaries without receiving generic filesystem, shell, or editing powers.

## Start The MCP Server

Run this from the LocalScope repository root:

```powershell
cd D:\claw-local-task-governor
python -m adapters.mcp.server
```

The server uses stdout for MCP protocol JSON. Human logs or debug messages must go to stderr.

## OpenCode Configuration Template

OpenCode MCP configuration can vary by installation and version. Use this as a conceptual template and adjust the file location or exact format for your local OpenCode setup.

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

If you use a virtual environment, point `command` to that interpreter instead:

```json
{
  "mcpServers": {
    "localscope": {
      "command": "D:/claw-local-task-governor/.venv/Scripts/python.exe",
      "args": ["-m", "adapters.mcp.server"],
      "cwd": "D:/claw-local-task-governor"
    }
  }
}
```

Recommended server name:

```text
localscope
```

Recommended working directory:

```text
D:/claw-local-task-governor
```

## Available Tools

Main tool:

```text
localscope_audit
```

Read-only query tools:

```text
localscope_status
localscope_report
localscope_graph_info
```

LocalScope intentionally does not expose:

```text
read_file
write_file
run_command
apply_patch
shell
exec
```

This keeps OpenCode focused on high-level audit workflows and avoids saturating local models with broad low-level tool schemas.

## Tool Arguments

### localscope_audit

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

```json
{
  "limit": 5
}
```

This reads recent LocalScope reports and memory status. It does not run a new audit.

### localscope_report

```json
{
  "report_path": "D:/claw-local-task-governor/reports/audit-YYYYMMDD-HHMMSS.json"
}
```

For safety, report paths are restricted to LocalScope-owned `reports/audit-*.json` and `reports/audit-*.md` files.

### localscope_graph_info

```json
{
  "path": "D:/ruta/al/proyecto"
}
```

This checks for existing Graphify output. It does not run Graphify automatically.

## Smoke Test

You can verify that the server starts and lists the expected tools without OpenCode:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
'@ | python -m adapters.mcp.server
```

Expected tool names:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

No human log lines should appear in stdout.

## Prompt Examples For OpenCode

Example 1:

```text
Usa LocalScope para auditar este proyecto en modo read-only. Ejecuta localscope_audit con max_tasks=5 y resume el reporte final.
```

Example 2:

```text
Consulta localscope_graph_info para ver si hay contexto Graphify disponible antes de auditar.
```

Example 3:

```text
Lee el último reporte con localscope_report y resume hallazgos críticos y altos.
```

## Graphify Relationship

Graphify can generate project knowledge graph files such as:

```text
graphify-out/graph.json
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
```

LocalScope can consume those files as optional context when `use_graphify` is `true`. LocalScope MCP does not replace a Graphify MCP server and does not run Graphify automatically.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| OpenCode no detecta server MCP | Confirm the MCP config points to `python` with args `["-m", "adapters.mcp.server"]` and `cwd` set to the LocalScope repo root. |
| Python no está en PATH | Use the full Python or virtualenv interpreter path in `command`. |
| Problema con working directory | Set `cwd` to `D:/claw-local-task-governor`; imports fail if the server starts elsewhere without the repo on `PYTHONPATH`. |
| Ollama apagado | Run `ollama list`, `ollama serve`, then `python -m governor.main ollama-test`. Audit errors are returned as structured JSON. |
| Paths Windows con espacios | Keep paths quoted in OpenCode config/tool calls, or use forward slashes such as `D:/Mis Proyectos/App Demo`. |
| Graphify ausente | This is allowed. `localscope_graph_info` returns `available: false`, and audits continue with the filesystem scanner. |
| Auditoría tarda mucho | Lower `max_tasks`, use memory reuse, and prefer `localscope_status` or `localscope_report` for follow-up queries. |
| JSON/logs mezclados | Do not add debug `print()` calls to stdout. MCP protocol responses must stay on stdout; logs belong on stderr. |

## Current Limitations

- MCP support is experimental and implemented as a minimal stdio JSON-RPC server.
- Long audits are synchronous.
- Ollama must be running for new model analysis unless results are reused from memory.
- Graphify is optional and only consumed when existing output is present.
- LocalScope does not edit files, apply patches, or run arbitrary commands through MCP.
