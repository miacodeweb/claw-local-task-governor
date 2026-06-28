# LocalScope Release MVP v0.1.0-rc1

## What Is LocalScope v0.1.0-rc1

LocalScope is a local-first, read-only project and folder analysis suite for AI agents and local models. It scans projects, creates microtasks, uses Ollama for local model analysis, validates output with JSON Guard, stores incremental memory, and generates deterministic Markdown/JSON reports.

Version v0.1.0-rc1 is the first local release candidate for the MVP. It is installable via `python -m pip install -e .` with the `localscope` CLI command. This RC is for local validation only; do not publish it to PyPI or create a remote GitHub release until the stable v0.1.0 checklist passes.

## Features Included

### Core Analysis

| Feature | Command | Description |
|---|---|---|
| Scan | `scan` | Walk a folder, detect profile, compute file hashes |
| Tasks | `tasks` | Generate prioritized microtasks from scanner output |
| Run tasks | `run-tasks` | Execute pending tasks via Ollama |
| Audit | `audit` | Full flow: scan → tasks → run-tasks → report |
| Report | `report` | Reduce task results into final reports |

### Model Management

| Feature | Command | Description |
|---|---|---|
| Ollama test | `ollama-test` | Verify local Ollama connectivity |
| Model stats | `model-stats` | Show operational metrics per model |
| Prompts | `prompts` | List and recommend prompt variants |
| Model recommendations | `model-recommendations` | Recommend best model/prompt/limits per profile |
| Benchmark models | `benchmark-models` | Compare models on a project fixture |
| Benchmark profile | `benchmark-profile` | Compare models per project type via calibration fixtures |
| Calibrate models | `calibrate-models` | Warm-up recommendations across profiles |

### Operations

| Feature | Command | Description |
|---|---|---|
| Logs | `logs` | Structured JSONL logging (summary, errors, tasks) |
| Graph info | `graphify-info` | Inspect optional Graphify output |
| Suggest patch | `suggest-patch` | Generate reviewable patch proposals (never applied) |

### Adapters

| Adapter | Entry point | Description |
|---|---|---|
| OpenClaw | `python -m adapters.openclaw.local_scope_audit` | Wrapper CLI returning JSON |
| OpenCode | `python -m adapters.opencode.local_scope_audit` | Wrapper CLI returning JSON |
| MCP (experimental) | `python -m adapters.mcp.server` | stdio MCP server with 4 tools |

### MCP Tools

- `localscope_audit` — full audit
- `localscope_status` — recent status query
- `localscope_report` — read existing report
- `localscope_graph_info` — Graphify diagnostics

### Context Providers

- **Filesystem scanner** — always on, no dependencies
- **Graphify** — optional structural context from `graphify-out/`

## Security

LocalScope is read-only by default:

- Never modifies analyzed files.
- Never applies patches automatically (`suggest-patch` saves diffs without applying).
- Never exposes `read_file`, `write_file`, `run_command`, `shell`, `exec`, or `apply_patch` as adapter/MCP tools.
- Adapters enforce `read_only=true` (rejects `read_only=false`).
- Project paths are validated (must exist, be directories, not filesystem roots).
- `max_tasks` bounded 1–100.
- Secret-like files (`.env`) are flagged but their content is never included in reports.
- Logs redact API keys, tokens, and passwords automatically.

## Installation

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[test]
Copy-Item config.example.yaml config.yaml

# Verify
localscope --help
```

Edit `config.yaml` to set your Ollama model and preferences.

## Smoke Tests (Manual)

```powershell
# CLI entry point
localscope --help

# Core flow (dry-run, no model calls)
localscope scan tests/fixtures/sample_project
localscope tasks tests/fixtures/sample_project
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run

# Model recommendations
localscope model-recommendations --profile python
localscope model-recommendations --latest-benchmark --json

# Logs
localscope logs summary

# Ollama connectivity
localscope ollama-test
```

## Usage With Ollama

```powershell
# Verify Ollama
ollama list
localscope ollama-test

# Benchmark installed models on a fixture
localscope benchmark-models tests/fixtures/sample_project --all-ollama --max-tasks 3

# Benchmark per project profile
localscope benchmark-profile python javascript --all-ollama --max-tasks 5

# Calibrate and store recommendations
localscope calibrate-models --profiles python --all-ollama --max-tasks 5

# Run audit with benchmark recommendations
localscope audit path/to/project --use-benchmark-recommendations --max-tasks 5
```

## Usage With OpenCode (MCP)

```powershell
# Start MCP server
python -m adapters.mcp.server

# OpenCode config (conceptual)
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

## Usage With OpenClaw

```powershell
python -m adapters.openclaw.local_scope_audit --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

## Limitations

- **Ollama only** — no other local model providers yet.
- **Tasks are small and bounded** — `max_chars_per_file` limits file content sent to models.
- **Confidence requires data** — `model-recommendations` needs prior benchmark/profile data to be useful.
- **No automatic model downloads** — models must be pulled manually with `ollama pull`.
- **No fine-tuning** — model profiles track operational stats only.
- **No benchmark warm-up** — the first run per model session may be slower (cold start).
- **`python -m governor.main`** is the compatibility path; migrate to `localscope` CLI.
- **MCP is experimental** — minimal implementation, no external MCP package dependency.
- **Graphify is optional** — scanner-based flow works without it.
- **Windows `pytest-of-crist` temp dir** — may require `--basetemp` flag if permissions are restricted.

## Roadmap Next

1. Extract `read_text_limited`/`resolve_task_file` from `task_runner` to break remaining import cycle.
2. Add non-Ollama model providers.
3. Stabilize MCP server with formal MCP package integration.
4. Rename `governor/` package to `localscope/`.
5. GitHub Actions CI.
6. `pip install localscope` from PyPI.
