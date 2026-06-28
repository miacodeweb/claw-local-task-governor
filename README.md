# LocalScope

LocalScope is a local-first project and folder analysis suite for AI agents and local models. It scans projects, creates microtasks, uses local models through Ollama, validates model output with JSON Guard, stores incremental memory, optionally consumes Graphify knowledge graphs, and generates Markdown/JSON reports.

The original MVP name was **Claw Local Task Governor**. That name is now treated as historical. The current product/core concept is **LocalScope**.

OpenClaw is no longer the center of the project. OpenClaw and OpenCode are adapters. The core remains generic and local-first.

## What Is LocalScope?

LocalScope analyzes local folders, codebases, configuration trees, and mixed project structures without sending the whole project to one large prompt. It turns a project into small read-only tasks, runs limited model analysis through local providers, validates every model response, stores reusable results, and produces deterministic reports.

The current internal Python package is still `governor/` for MVP compatibility. Do not treat that package name as the final brand.

## Core Capabilities

- Local filesystem scanner.
- Task queue.
- Microtask runner.
- Ollama provider.
- JSON Guard.
- SQLite memory.
- Deterministic Markdown and JSON reports.
- Graphify optional context provider.
- Read-only by default.
- Adapter architecture.
- Extensible model providers (Ollama + OpenAI-compatible).

## Primary Adapters

- **OpenClaw:** wrapper CLI in `adapters/openclaw/local_scope_audit.py`, with `openclaw/local_project_audit.py` kept as a compatibility shim.
- **OpenCode:** wrapper CLI in `adapters/opencode/local_scope_audit.py`.

Future integrations may include MCP, but MCP is not part of the current MVP.

## Supported Targets

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

## Safety

LocalScope is read-only toward analyzed targets:

- It does not modify analyzed files.
- It does not apply patches.
- It does not execute shell commands over the analyzed project.
- It does not expose `read_file`, `write_file`, `run_command`, or `apply_patch` as adapter tools.
- It only writes LocalScope-owned outputs such as `reports/` and `data/memory.sqlite`.

## Current Commands

Recommended one-command audit:

```powershell
python -m governor.main audit D:\ruta\al\proyecto --profile auto --max-tasks 5
```

Dry-run without model calls:

```powershell
python -m governor.main audit D:\ruta\al\proyecto --profile auto --max-tasks 5 --dry-run
```

Step-by-step commands are still available for diagnostics:

```powershell
python -m governor.main scan D:\ruta\al\proyecto
python -m governor.main tasks D:\ruta\al\proyecto
python -m governor.main ollama-test
python -m governor.main run-tasks D:\ruta\al\proyecto --max-tasks 5
python -m governor.main report D:\ruta\al\proyecto
```

Use benchmark-based model recommendations:

```powershell
python -m governor.main audit path/to/project --profile auto --max-tasks 5 --use-benchmark-recommendations
python -m governor.main audit path/to/project --profile auto --max-tasks 5 --model qwen3:8b
```

## Model Benchmarking And Recommendations

LocalScope can compare installed Ollama models to help you pick the best one for each project type:

```powershell
# Benchmark all installed models against calibration fixtures
python -m governor.main benchmark-profile python --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Warm-up/calibrate recommendations across profiles
python -m governor.main calibrate-models --profiles python javascript config_files --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Show recommendations with confidence level
python -m governor.main model-recommendations --profile python
python -m governor.main model-recommendations --latest-benchmark --json
```

Confidence levels: `none` (0 samples) → `low` (1-4) → `medium` (5-14) → `high` (15+).

Warnings:
- Benchmark compares installed models only — no automatic downloads.
- No fine-tuning happens.
- `config.yaml` is never modified.
- Results depend on fixture content and local hardware.

## Web UI

A local read-only dashboard for viewing reports, logs, benchmarks, and model recommendations:

```powershell
localscope webui
```

Opens browser at `http://127.0.0.1:8765`. No external dependencies. Read-only — never modifies projects.

Generated outputs:

```text
reports/scan_result.json
reports/tasks.json
reports/task_results.json
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
reports/benchmarks/benchmark-YYYYMMDD-HHMMSS.json
reports/benchmarks/profile-benchmark-YYYYMMDD-HHMMSS.json
data/memory.sqlite
```

## Quick Install

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
Copy-Item config.example.yaml config.yaml
```

After install, use:

```powershell
localscope --help
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope audit D:\ruta\al\proyecto --max-tasks 5
localscope model-recommendations
localscope logs summary
```

`python -m governor.main` remains supported for compatibility:

```powershell
python -m governor.main audit tests/fixtures/sample_project --max-tasks 3 --dry-run
```

If Windows cannot find `localscope` after installation, check the active Python scripts directory:

```powershell
python -m site --user-base
```

Then ensure the matching `Scripts` folder is on `PATH`, or run the compatible `python -m governor.main ...` form.

The repository folder may still be named `claw-local-task-governor` during the transition. That is temporary compatibility, not the product identity.

## Optional Graphify Flow

Graphify is an optional context provider. LocalScope does not run Graphify automatically.

```powershell
graphify D:\ruta\al\proyecto
python -m governor.main graphify-info D:\ruta\al\proyecto
python -m governor.main tasks D:\ruta\al\proyecto
```

If `graphify-out/graph.json` is missing or invalid, the scanner-only flow still works.

## OpenClaw Adapter

Current OpenClaw integration is a wrapper CLI:

```powershell
python -m adapters.openclaw.local_scope_audit --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

Legacy compatibility shim:

```powershell
python openclaw/local_project_audit.py --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

It returns JSON with report paths, counts, summary, and errors. See [openclaw/README_OPENCLAW.md](openclaw/README_OPENCLAW.md).

## OpenCode Adapter

Current OpenCode integration is also a wrapper CLI:

```powershell
python -m adapters.opencode.local_scope_audit --path D:\ruta\al\proyecto --profile auto --max-tasks 5 --read-only true
```

It returns JSON only on stdout so OpenCode can consume the response as an external tool. See [adapters/opencode/README.md](adapters/opencode/README.md).

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Windows 10 + WSL + Ollama](docs/WINDOWS_WSL_OLLAMA.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [OpenClaw Adapter](openclaw/README_OPENCLAW.md)
- [OpenCode Adapter](adapters/opencode/README.md)

## Troubleshooting Shortcuts

- Ollama does not respond: run `ollama list`, `ollama serve`, then `python -m governor.main ollama-test`.
- Model not found: run `ollama pull qwen2.5-coder:7b` or change `config.yaml`.
- Invalid JSON: reduce `ollama.max_chars_per_file`, run fewer tasks, or use a stronger local model.
- Graphify not detected: check `graphify-out/graph.json` and run `graphify-info`.
- Windows paths with spaces: quote paths, for example `"D:\Mi Proyecto"`.
- UTF-8 BOM in PowerShell files: the reader handles BOM for JSON task files; prefer UTF-8 without BOM for generated config.

## Tests

```powershell
pytest
```
