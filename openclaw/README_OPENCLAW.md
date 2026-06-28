# OpenClaw Adapter For LocalScope

This folder contains the initial OpenClaw adapter for LocalScope.

Current status: wrapper CLI, not a native OpenClaw plugin yet.

LocalScope is the core product. OpenClaw is one adapter that can call the core audit flow.

## Tool

`local_scope_audit` is the primary high-level wrapper exposed for a full local audit.

`local_project_audit` remains as a compatibility alias for older OpenClaw configurations.

It runs this internal read-only flow:

```text
scan -> tasks -> run-tasks -> report
```

It does not expose low-level tools such as `read_file`, `write_file`, `run_command`, or `apply_patch`.

## Arguments

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

Supported profiles:

```text
auto, general, php, wordpress, javascript, python, java, docker, windows_folder, linux_folder
```

Supported modes:

```text
general, security, code_quality, config_audit
```

`read_only` must be `true`. If it is `false`, the wrapper returns JSON with `status: "failed"` and does not run an audit.

## Manual Test

From the repository root:

```powershell
python adapters/openclaw/local_scope_audit.py --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

Equivalent module form:

```powershell
python -m adapters.openclaw.local_scope_audit --path "D:/path/to/project" --max-tasks 5 --profile auto --read-only true
```

Optional flags:

```powershell
python -m adapters.openclaw.local_scope_audit --path "D:/path/to/project" --profile python --mode security --max-tasks 3 --use-memory true --use-graphify true --read-only true
```

Legacy shim:

```powershell
python openclaw/local_project_audit.py --path "D:/path/to/project" --profile auto --max-tasks 5 --read-only true
```

## Response

The wrapper always prints JSON to stdout. Logs or debug output must go to stderr.

```json
{
  "status": "completed",
  "adapter": "openclaw",
  "project_path": "D:/path/to/project",
  "profile_detected": "python",
  "report_markdown": "D:/localscope/reports/audit-YYYYMMDD-HHMMSS.md",
  "report_json": "D:/localscope/reports/audit-YYYYMMDD-HHMMSS.json",
  "tasks_processed": 5,
  "reused": 0,
  "json_valid": 5,
  "json_repaired": 0,
  "json_failed": 0,
  "summary": "Audit reduced 5 analyzed files with 0 actionable findings.",
  "errors": []
}
```

If Ollama is unavailable, the wrapper still prints JSON. The audit may complete with failed model tasks, or fail early if the error happens before task execution.

## Safety

- The adapter is read-only.
- The wrapper rejects `read_only=false`.
- It writes only LocalScope-owned outputs such as `reports/scan_result.json`, `reports/tasks.json`, `reports/task_results.json`, and final audit reports.
- It does not edit the audited project.
- It does not run shell commands against the audited project.
- It does not expose file editing or patch application.

## Connecting To OpenClaw

Until a native plugin is implemented, configure OpenClaw to call this wrapper as one external command:

```powershell
python -m adapters.openclaw.local_scope_audit --path "<PROJECT_PATH>" --profile auto --mode general --max-tasks 5 --read-only true
```

OpenClaw should parse stdout as JSON and use `report_markdown`, `report_json`, and `summary` for its final response.

Recommended behavior inside OpenClaw:

- Treat `local_scope_audit` as one high-level audit tool.
- Do not expose scanner, task runner, JSON Guard, file reading, shell, or patch operations as separate OpenClaw tools.
- Ask LocalScope to audit, then use the generated Markdown/JSON report for the answer.
- Keep the operation read-only and reject any request to modify files through this adapter.

## Prompt Examples For OpenClaw

Prompt 1:

```text
Usa LocalScope mediante el adaptador local_scope_audit para auditar esta carpeta en modo read-only. No modifiques archivos. Devuélveme un resumen del reporte Markdown/JSON generado.
```

Prompt 2:

```text
Primero consulta si existe contexto Graphify. Luego ejecuta LocalScope con max_tasks=5 y resume hallazgos críticos, altos y medios.
```

Prompt 3:

```text
Ejecuta LocalScope sobre este proyecto con perfil auto. Si Ollama no responde, informa el error sin intentar modificar nada.
```

## Current Limits

- This is not a native OpenClaw plugin yet.
- OpenCode is handled by its own LocalScope adapter under `adapters/opencode/`.
- MCP is available as a separate experimental adapter under `adapters/mcp/`; OpenClaw can keep using this CLI wrapper unless native MCP support is configured later.
- Patch generation and file editing are not exposed.
- Graphify is optional and is only read if existing outputs are present.
- The final report reduce is deterministic; it does not ask a model to write the report.

## TODO For Native Plugin

- Map this wrapper contract into OpenClaw's native plugin/tool manifest format.
- Keep only the single high-level `local_scope_audit` surface, with `local_project_audit` as an optional compatibility alias.
- Preserve `read_only=true` as mandatory.
- Keep low-level file and shell tools unavailable.
