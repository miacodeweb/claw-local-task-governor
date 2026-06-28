# LocalScope MCP Plan

This document defines the MCP integration plan for LocalScope.

Current status: an experimental minimal MCP stdio server exists with four high-level read-only tools:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

No low-level filesystem, shell, or editing tools are exposed.

## Why MCP Is Useful

MCP can make LocalScope available as a standard external tool for compatible agents such as OpenCode and, if applicable later, OpenClaw.

The main value is not exposing more power. The value is exposing fewer, safer, higher-level tools:

- Let compatible agents trigger LocalScope audits without shell-specific wrapper details.
- Keep the tool surface small so local models are not overloaded by many schemas.
- Avoid giving agents generic filesystem, shell, or edit capabilities.
- Reuse the same LocalScope core flow already used by CLI, OpenClaw, and OpenCode wrappers.
- Make OpenCode integration cleaner because many agent environments already understand MCP-style tools.
- Keep OpenClaw as an adapter rather than the center of the system.

LocalScope should continue to do the hard stabilizing work: scanning, task planning, JSON Guard validation, SQLite memory reuse, Graphify context consumption, and deterministic reports.

## Scope

The MCP server should expose LocalScope as a read-only analysis service.

It should not become a general-purpose filesystem or command server.

MCP tools:

```text
localscope_audit      implemented experimentally
localscope_status     implemented experimentally
localscope_report     implemented experimentally
localscope_graph_info implemented experimentally
```

Forbidden MCP tools:

```text
read_file
write_file
run_command
apply_patch
shell
exec
```

## Minimal Tools

### localscope_audit

Runs the full LocalScope flow:

```text
scan -> tasks -> run-tasks -> report
```

Request:

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

Response:

```json
{
  "status": "completed|failed",
  "adapter": "mcp",
  "project_path": "string",
  "profile_detected": "string",
  "report_markdown": "string",
  "report_json": "string",
  "tasks_processed": 0,
  "reused": 0,
  "json_valid": 0,
  "json_repaired": 0,
  "json_failed": 0,
  "summary": "string",
  "errors": []
}
```

The implementation should reuse `adapters/common/run_audit.py` instead of duplicating the audit flow.

### localscope_status

Returns recent audit status without rescanning or reanalyzing.

Request:

```json
{
  "limit": 5
}
```

Response includes:

```json
{
  "status": "completed|no_audits|failed",
  "recent_audits": [],
  "current_task_results": {},
  "memory": {},
  "summary": "string",
  "errors": []
}
```

This should be based on existing report/status helpers, not a new database format.

### localscope_report

Reads an existing LocalScope report summary.

Request:

```json
{
  "report_path": "string"
}
```

Response should include report paths, summary, counts, and errors. It must not re-run analysis.

For safety, the current implementation only accepts LocalScope-owned `reports/audit-*.json` or `reports/audit-*.md` paths inside the repository `reports/` folder.

### localscope_graph_info

Returns Graphify diagnostics for a project path without running Graphify.

Request:

```json
{
  "path": "string"
}
```

Response should mirror `python -m governor.main graphify-info` as structured JSON:

```json
{
  "available": true,
  "graph_path": "string",
  "nodes_count": 0,
  "edges_count": 0,
  "referenced_files": [],
  "important_files": [],
  "central_nodes": [],
  "warnings": []
}
```

## Security Model

The MCP server must preserve the current LocalScope safety model.

Rules:

- `read_only` defaults to `true`.
- `read_only=false` is rejected.
- `max_tasks` must be between `1` and `100`.
- Project paths are normalized, must exist, must be directories, and must not be filesystem roots.
- Quoted Windows paths and paths with spaces are normalized before validation.
- `localscope_report` only reads LocalScope-owned `reports/audit-*.json` or `reports/audit-*.md` files.
- No file editing.
- No arbitrary shell commands.
- No general filesystem browsing tools.
- No low-level file read/write APIs.
- No patch application.
- No secret dumping.
- Validate project paths before use.
- Keep operations inside the requested project and LocalScope-owned output directories.
- Keep stdio clean for MCP transport.
- Return structured errors instead of crashing.

MCP must not expose raw `.env`, credential files, private keys, tokens, or other secrets as generic content. LocalScope can scan metadata and apply existing redaction/truncation rules, but it should not become a secret exfiltration surface.

## Relationship With Existing Wrappers

Current wrappers remain useful:

```text
python -m governor.main audit ...
python -m adapters.openclaw.local_scope_audit ...
python -m adapters.opencode.local_scope_audit ...
```

MCP should not replace those immediately. It should add a third adapter path that uses the same common contract.

Recommended future structure:

```text
adapters/
  common/
  openclaw/
  opencode/
  mcp/
```

The MCP implementation should call shared functions in `adapters/common/`.

## Relationship With Graphify

Graphify remains an optional structural context provider.

Graphify can continue to generate:

```text
graphify-out/graph.json
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
```

LocalScope can consume that output to prioritize tasks, enrich reports, and reduce unnecessary model calls.

If Graphify later exposes its own MCP server, LocalScope should not duplicate it. The roles should stay separate:

- Graphify MCP: project graph generation and structural graph queries.
- LocalScope MCP: audits, JSON Guard validation, memory reuse, Graphify consumption, and report generation.

LocalScope should keep scanner fallback behavior when Graphify is missing or invalid.

## Implementation Phases

### Phase 1: CLI Wrappers

Status: implemented.

- OpenClaw wrapper: `adapters/openclaw/local_scope_audit.py`.
- OpenCode wrapper: `adapters/opencode/local_scope_audit.py`.
- Shared contract: `adapters/common/`.

### Phase 2: Experimental MCP Server

Status: implemented for audit plus read-only query tools.

Path:

```text
adapters/mcp/
  server.py
  README.md
```

Start command:

```bash
python -m adapters.mcp.server
```

Implemented tools:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

`localscope_audit` uses the existing common request and response contract. The query tools read existing report or Graphify outputs only and do not trigger new analysis.

Dependency decision: no external MCP package is used yet. The current server is a small line-delimited JSON-RPC stdio adapter because the local environment does not include an `mcp` Python package and LocalScope currently has no runtime dependencies.

### Phase 3: OpenCode Configuration

Status: documented in `adapters/mcp/README.md`, `adapters/opencode/README.md`, and `adapters/opencode/MCP_SETUP.md`.

OpenCode should start the server with:

```bash
python -m adapters.mcp.server
```

Conceptual configuration:

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

This is a template. The exact OpenCode config location and syntax can vary by local installation, so the command, args, and working directory are the important parts:

```text
server name: localscope
command: python
args: -m adapters.mcp.server
working directory: LocalScope repository root
```

OpenCode should primarily call:

```text
localscope_audit
```

It may also call read-only query tools:

```text
localscope_status
localscope_report
localscope_graph_info
```

Example call:

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

The reason for exposing only a few high-level tools is to avoid saturating local models with many small tool schemas. LocalScope remains the orchestrator for scanner, tasks, Ollama, JSON Guard, memory, optional Graphify context, and deterministic reports.

LocalScope MCP must not expose:

```text
read_file
write_file
run_command
apply_patch
shell
exec
```

Keep the CLI wrapper as fallback while MCP is tested.

Smoke test without OpenCode:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
'@ | python -m adapters.mcp.server
```

The response should include only:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

Troubleshooting topics to keep documented:

- MCP server does not start.
- Python path or virtual environment is wrong.
- Windows paths contain spaces.
- Ollama is off or the model is missing.
- JSON protocol output is mixed with logs.
- OpenCode does not see `localscope_audit`.

### Phase 4: OpenClaw Configuration If Applicable

If OpenClaw supports MCP in the local setup, document how to connect it.

If not, keep the current CLI wrapper and do not invent a fake native integration.

### Phase 5: Status, Report, And Graph Info Tools

Status: implemented experimentally.

Add read-only query tools:

```text
localscope_status
localscope_report
localscope_graph_info
```

These tools do not trigger a full audit.

## Technical Risks

- MCP stdio logging can break protocol if human logs are written to stdout.
- Tool schemas can become too broad and overwhelm local models.
- Generic filesystem tools would weaken the safety model.
- Path handling differs across Windows, WSL, and Linux.
- Long audit runs may need progress/status handling without streaming unsafe logs.
- Ollama failures must remain structured and non-fatal.
- Graphify may have multiple output shapes; LocalScope must keep defensive parsing.

## Recommended First Implementation Order

1. Create `adapters/mcp/README.md` and `adapters/mcp/server.py`.
2. Keep `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info` as the complete basic MCP surface.
3. Use `adapters/common/AuditRequest`, `AuditResponse`, and `run_audit` for audits.
4. Reject `read_only=false`.
5. Add tests for JSON-serializable responses, path errors, query-only behavior, and forbidden tool names.
6. Keep OpenCode setup documentation current.
7. Harden these four tools before adding any new MCP tool.
