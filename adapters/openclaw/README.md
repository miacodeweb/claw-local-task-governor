# LocalScope OpenClaw Adapter

This adapter lets OpenClaw call LocalScope through one high-level read-only tool.

LocalScope is the independent audit suite. OpenClaw is an adapter that can invoke it and consume its JSON/report outputs.

Primary tool:

```text
local_scope_audit
```

Compatibility alias:

```text
local_project_audit
```

## Manual Command

From the repository root:

```powershell
python adapters/openclaw/local_scope_audit.py --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

Equivalent module form:

```powershell
python -m adapters.openclaw.local_scope_audit --path "D:\ruta\al\proyecto" --profile auto --mode general --max-tasks 5 --read-only true
```

The historical wrapper remains available:

```powershell
python openclaw/local_project_audit.py --path "D:\ruta\al\proyecto" --profile auto --max-tasks 5 --read-only true
```

## Arguments

```text
--path
--profile
--mode
--max-tasks
--use-memory
--use-graphify
--read-only
```

`--read-only true` is mandatory. `read_only=false` is rejected before the audit runs.

## Contract

The command writes JSON only to stdout:

```json
{
  "status": "completed",
  "adapter": "openclaw",
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

OpenClaw should parse stdout as JSON. Human logs and debug output should not be written to stdout.

## Conceptual OpenClaw Usage

Configure OpenClaw to call `local_scope_audit` as one external high-level tool. Do not expose LocalScope internals as separate OpenClaw tools.

Recommended external command shape:

```powershell
python adapters/openclaw/local_scope_audit.py --path "<PROJECT_PATH>" --profile auto --mode general --max-tasks 5 --use-memory true --use-graphify true --read-only true
```

OpenClaw should:

- call the adapter with the target project path;
- parse stdout as JSON;
- use `summary`, `report_markdown`, and `report_json` for the final answer;
- keep the operation read-only;
- avoid requesting direct file edits, shell commands, or patch application from this adapter.

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

## Safety

- `read_only` must be `true`.
- `read_only=false` is rejected with a JSON failure response.
- The adapter does not expose `read_file`, `write_file`, `run_command`, or `apply_patch`.
- The adapter does not expose `shell` or `exec`.
- The audited project is not edited.
- LocalScope writes only its own outputs under `reports/` and `data/`.

## Limitations

- This is a CLI adapter, not a native OpenClaw plugin yet.
- MCP exists as a separate experimental LocalScope adapter, but this OpenClaw package remains a CLI wrapper unless a native OpenClaw plugin is added later.
- Graphify is optional and only consumed if its output already exists.
- OpenCode is handled separately by `adapters/opencode/`.
