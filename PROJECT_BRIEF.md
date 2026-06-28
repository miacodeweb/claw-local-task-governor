# LocalScope — Project Brief

**Version:** v0.1.0-rc1 MVP release candidate

## Identity

- **Product name:** LocalScope
- **Historical name:** Claw Local Task Governor (MVP phase only)
- **Internal package:** `governor/` (temporary; eventual rename to `localscope/`)
- **Type:** local-first, read-only project/folder analysis suite

## Objective

Analyze local folders, codebases, config trees, and mixed projects via small read-only microtasks processed by local models (Ollama). No full-project prompts. No remote APIs. Deterministic Markdown/JSON reports.

## Core Components

| Component | File | Role |
|---|---|---|
| Scanner | `governor/scanner.py` | Walk folder, detect profile, compute hashes, produce `scan_result.json` |
| Profile detector | `governor/profile_detector.py` | Auto-detect project type (general, php, wordpress, javascript, python, java, docker, windows_folder, linux_folder) |
| Model profiles | `governor/model_profiles.py` | Operational stats per model/task/profile (success rate, repair rate, avg response ms) |
| Task queue | `governor/task_queue.py` | Convert scan into prioritized pending tasks (`tasks.json`) |
| Prioritizer | `governor/prioritizer.py` | Priority from scanner signals + optional Graphify signals |
| Task runner | `governor/task_runner.py` | Execute pending tasks via Ollama, reuse memory |
| Ollama provider | `governor/ollama_client.py` | Native `http://127.0.0.1:11434/api/chat` provider; first local provider |
| JSON Guard | `governor/json_guard.py` | Parse responses, extract JSON, remove fences, repair commas, validate against schemas |
| SQLite memory | `governor/memory.py` | `data/memory.sqlite` — reuse results by project path + file hash + model + prompt + task type |
| Prompt manager | `governor/prompt_manager.py` | Controlled prompt variants (v1, v2_strict_json, v3_short_schema) |
| Prompt renderer | `governor/prompt_renderer.py` | Render prompts with optional Graphify context |
| Adaptive limits | `governor/adaptive_limits.py` | Adjust max_chars per file from model stats |
| Report writer | `governor/report_writer.py` | Write Markdown/JSON audit reports |
| Reducer | `governor/reducer.py` | Build final report from task results |
| Patch suggester | `governor/patch_suggester.py` | Generate reviewable patches without applying them |
| Safety | `governor/safety.py` | Centralized validation for adapter inputs |
| Model providers | `governor/providers/` | Extensible provider architecture (Ollama + OpenAI-compatible) |
| Model benchmark | `governor/model_benchmark.py` | Compare Ollama models on a project fixture with scoring |
| Profile benchmark | `governor/profile_benchmark.py` | Compare models per project type using calibration fixtures |
| Recommendations | `governor/model_recommendations.py` | Recommend model/prompt/limits from benchmark data with confidence levels |

## Context Providers

- **Filesystem scanner** — always-on, no dependencies
- **Graphify** — optional; reads `graphify-out/graph.json`, `GRAPH_REPORT.md`, `graph.html` if present. Never runs Graphify automatically. Scanner falls back gracefully if Graphify output is missing/invalid.

## Adapters (outside core)

| Adapter | Path | Entry point |
|---|---|---|
| OpenClaw | `adapters/openclaw/local_scope_audit.py` | `python -m adapters.openclaw.local_scope_audit` |
| OpenCode | `adapters/opencode/local_scope_audit.py` | `python -m adapters.opencode.local_scope_audit` |
| MCP (experimental) | `adapters/mcp/server.py` | `python -m adapters.mcp.server` |
| Shared contract | `adapters/common/run_audit.py` | Shared `AuditRequest` / `AuditResponse` / `run_audit` |

MCP tools: `localscope_audit`, `localscope_status`, `localscope_report`, `localscope_graph_info`.

## Security (non-negotiable)

- **Read-only toward analyzed targets** — never modifies analyzed files
- **No `apply_patch`** — patches are proposed but never applied automatically
- **No `write_file`** — only writes LocalScope-owned outputs (`reports/`, `data/`)
- **No `run_command`** / **no `shell`** / **no `exec`** — no arbitrary command execution
- **No generic filesystem** — adapters must not expose `read_file`, `write_file`, `run_command`, `shell`, `exec`, `apply_patch`
- **`read_only=false` is rejected** in adapters
- **`max_tasks` bounded 1–100** in adapters
- **Paths validated** — must exist, be directories, not filesystem roots

## Main Commands

All via `python -m governor.main <command>`:

| Command | Purpose |
|---|---|---|
| `audit` | Full flow: scan → tasks → run-tasks → report (recommended one-shot) |
| `scan` | Scan project, write `scan_result.json` |
| `tasks` | Generate tasks from scan, write `tasks.json` |
| `run-tasks` | Execute pending tasks with Ollama, write `task_results.json` |
| `report` | Reduce task results into final Markdown + JSON reports |
| `ollama-test` | Verify Ollama connectivity |
| `graphify-info` | Inspect optional Graphify output without running Graphify |
| `model-stats` | Show operational model stats from SQLite memory |
| `prompts` | List/recommend controlled prompt variants |
| `benchmark-models` | Compare installed Ollama models on a project fixture |
| `benchmark-profile` | Compare models per profile using calibration fixtures |
| `calibrate-models` | Warm-up recommendations per profile (wraps `benchmark-profile`) |
| `model-recommendations` | Show recommended model/prompt/limits with confidence level |
| `webui` | Start local read-only Web UI for reports, logs, and benchmarks |
| `providers list` | List registered model providers |
| `providers health` | Check health of all providers |
| `providers models` | List models for a provider |
| `openclaw-audit` | OpenClaw-compatible audit wrapper |
| `openclaw-status` | Recent audit status query |
| `openclaw-report` | Compact summary for existing report |
| `suggest-patch` | Generate reviewable patch proposals (does not apply) |

## Important Rules

- **No fine-tuning** — model profiles track operational stats only, never train models
- **No automatic model downloads** — Ollama models must be pulled manually
- **No copying Graphify into LocalScope** — Graphify is external; only consume its output
- **No generic filesystem exposure** — adapters expose high-level audit tools, not raw FS
- **No modifying analyzed projects** — LocalScope only writes its own output files

## Generated Outputs

```
reports/scan_result.json
reports/tasks.json
reports/task_results.json
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
reports/benchmarks/benchmark-YYYYMMDD-HHMMSS.json
reports/benchmarks/benchmark-YYYYMMDD-HHMMSS.md
reports/benchmarks/profile-benchmark-YYYYMMDD-HHMMSS.json
reports/benchmarks/profile-benchmark-YYYYMMDD-HHMMSS.md
data/memory.sqlite
```

## Confidence Levels

Model recommendations use 4 confidence tiers:

| Level | Samples | Description |
|---|---|---|
| `none` | 0 | No usable data; uses config.yaml default |
| `low` | 1–4 | Suggest running `calibrate-models` to improve |
| `medium` | 5–14 | Reasonable but more samples recommended |
| `high` | 15+ | Stable json_valid_rate and low model_fail_rate |

## Supported Targets

Windows/Linux folders, Java, Python, JS/TS, PHP, WordPress, Docker, server configs, documentation, generic mixed folders.

## Quick Install

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
Copy-Item config.example.yaml config.yaml

# Editable install provides the `localscope` command:
localscope --help
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope audit path/to/project --max-tasks 5
localscope model-recommendations
localscope logs summary

# Compatible fallback:
python -m governor.main audit tests/fixtures/sample_project --max-tasks 3 --dry-run
```

## Tests

```powershell
pytest
```
