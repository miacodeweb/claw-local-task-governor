# Getting Started With LocalScope

LocalScope is a local-first project and folder analysis suite. It scans local targets, creates microtasks, calls local models through Ollama, validates JSON with JSON Guard, reuses results from SQLite memory, and writes Markdown/JSON reports.

The internal package is still `governor/` during the MVP transition, so the CLI remains:

```text
python -m governor.main ...
```

## 1. Install

From PowerShell:

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
Copy-Item config.example.yaml config.yaml
```

The folder name can remain `claw-local-task-governor` for now. The product/core name is LocalScope.

After editable install:

```powershell
localscope --help
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope audit D:\ruta\al\proyecto --max-tasks 5
localscope model-recommendations --profile python

# Compatible fallback:
python -m governor.main audit tests/fixtures/sample_project --max-tasks 3 --dry-run
python -m governor.main audit D:\ruta\al\proyecto --max-tasks 5
```

If PowerShell still says `localscope` is not recognized, check where Python installs user scripts:

```powershell
# Find where the script was installed
python -m site --user-base
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"

# Test if it exists with full path
Test-Path "$env:APPDATA\Python\Python314\Scripts\localscope.exe"

# Run with full path as test
& "$env:APPDATA\Python\Python314\Scripts\localscope.exe" --help
```

To make `localscope` available system-wide on Windows:

1. Open **System Properties → Environment Variables**.
2. In **User variables**, edit `Path` and add:
   ```
   %APPDATA%\Python\Python314\Scripts
   ```
3. Restart your terminal.

Compatible fallback always works:
```powershell
python -m governor.main audit D:\ruta\al\proyecto --max-tasks 5
```

## 2. Configure Ollama

Edit `config.yaml` if you want a different local model:

```yaml
ollama:
  base_url: "http://127.0.0.1:11434"
  model: "qwen2.5-coder:7b"
  temperature: 0.1
  timeout_seconds: 120
  max_chars_per_file: 12000
```

Check Ollama:

```powershell
ollama list
python -m governor.main ollama-test
```

## 3. Run A Full Audit

Use quotes if the path contains spaces.

```powershell
python -m governor.main audit D:\ruta\al\proyecto --profile auto --max-tasks 5
```

This runs:

```text
scan -> tasks -> run-tasks -> report
```

For a safe preview without calling Ollama:

```powershell
python -m governor.main audit D:\ruta\al\proyecto --profile auto --max-tasks 5 --dry-run
```

The final report is written to:

```text
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
```

## 4. Step-By-Step Flow

Use quotes if the path contains spaces.

```powershell
python -m governor.main scan D:\ruta\al\proyecto
python -m governor.main tasks D:\ruta\al\proyecto
python -m governor.main ollama-test
python -m governor.main run-tasks D:\ruta\al\proyecto --max-tasks 5
python -m governor.main report D:\ruta\al\proyecto
```

## 5. Dry Run Before Model Calls

This validates task paths and prompt previews without calling Ollama:

```powershell
python -m governor.main run-tasks D:\ruta\al\proyecto --max-tasks 5 --dry-run
```

## 6. Supported Targets

LocalScope is intended for:

- Windows folders.
- Linux folders.
- Java projects.
- Python projects.
- JavaScript/TypeScript projects.
- PHP projects.
- WordPress.
- Docker.
- Server configuration files.
- Documentation.
- Generic mixed folders.

## 7. Force A Profile

Automatic detection is default, but you can force a profile:

```powershell
python -m governor.main scan D:\ruta\al\proyecto --profile python
python -m governor.main tasks D:\ruta\al\proyecto --profile python
python -m governor.main run-tasks D:\ruta\al\proyecto --max-tasks 5 --profile python
python -m governor.main audit D:\ruta\al\proyecto --profile python --max-tasks 5
```

Supported profiles:

```text
auto, general, php, wordpress, javascript, python, java, docker,
windows_folder, linux_folder, config_files
```

## 8. Optional Graphify Flow

Graphify is an optional context provider. LocalScope never copies Graphify code and does not run Graphify automatically.

```powershell
graphify D:\ruta\al\proyecto
python -m governor.main graphify-info D:\ruta\al\proyecto
python -m governor.main tasks D:\ruta\al\proyecto
```

If Graphify is missing, scanner-only task generation still works.

## 9. Adapters

Primary adapter status:

- OpenClaw: wrapper CLI exists.
- OpenCode: wrapper CLI exists.
- MCP: experimental stdio adapter exists for OpenCode-compatible clients.

Manual OpenClaw adapter test:

```powershell
python adapters/openclaw/local_scope_audit.py --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

The legacy OpenClaw shim remains available:

```powershell
python openclaw/local_project_audit.py --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

OpenClaw should treat LocalScope as one external high-level audit tool and parse stdout as JSON. See `adapters/openclaw/README.md` and `openclaw/README_OPENCLAW.md` for prompts and adapter details.

Manual OpenCode adapter test:

```powershell
python -m adapters.opencode.local_scope_audit --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

## 10. OpenCode MCP Quick Setup

Start the LocalScope MCP server from the repository root:

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

The exact OpenCode config file and format may vary by local installation. See `adapters/opencode/MCP_SETUP.md` for the full setup guide, smoke test, prompts, and troubleshooting.

Available MCP tools:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

LocalScope MCP does not expose `read_file`, `write_file`, `run_command`, `apply_patch`, `shell`, or `exec`.

## Read-Only Guarantee

LocalScope does not modify analyzed files, does not apply patches, and does not execute shell commands over the analyzed project. It writes only its own outputs under `reports/` and `data/`.

## Model Benchmarking And Calibration

LocalScope can compare installed Ollama models to find the best one per project type. This helps you choose between models like `qwen2.5-coder:7b`, `qwen3:8b`, or `gemma4:12b`.

### Quick calibration

```powershell
# Compare models on the Python calibration fixture
python -m governor.main benchmark-profile python --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Preview without calling Ollama
python -m governor.main benchmark-profile python --models qwen2.5-coder:7b --max-tasks 5 --dry-run

# Warm-up multiple profiles at once
python -m governor.main calibrate-models --profiles python javascript config_files --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Benchmark all installed models on all profiles
python -m governor.main benchmark-profile all --all-ollama --max-tasks 5
```

### View recommendations

```powershell
# Human-readable
python -m governor.main model-recommendations --profile python

# Machine-readable JSON
python -m governor.main model-recommendations --profile python --latest-benchmark --json
```

### Use recommendations in audits

```powershell
# Let LocalScope pick the best model from benchmark data
python -m governor.main audit D:\ruta\al\proyecto --use-benchmark-recommendations --max-tasks 5

# Or override manually
python -m governor.main audit D:\ruta\al\proyecto --model qwen3:8b --max-tasks 5
```

### Confidence levels

| Level | Samples | Meaning |
|---|---|---|
| `none` | 0 | No data yet — falls back to `config.yaml` |
| `low` | 1–4 | Not enough data — consider running `calibrate-models` |
| `medium` | 5–14 | Reasonable — more samples recommended |
| `high` | 15+ | Stable, reliable recommendation |

### Warnings

- Benchmark never downloads models — only tests already-installed ones.
- Benchmark never fine-tunes models.
- Benchmark never modifies `config.yaml`.
- Benchmark never applies patches or edits analyzed files.
- Results depend on calibration fixture content, model version, and local hardware.

## Web UI

LocalScope includes a read-only Web UI for viewing reports, logs, benchmarks, and recommendations:

```powershell
localscope webui

# Custom host/port
localscope webui --host 127.0.0.1 --port 9999

# Start without opening browser
localscope webui --no-browser
```

The Web UI binds to `127.0.0.1` by default (local only). It does not modify analyzed projects, does not expose dangerous endpoints, and uses zero external dependencies.
