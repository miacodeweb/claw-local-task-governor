# Changelog

## 0.1.0-rc1 - 2026-06-28

### Release Candidate

LocalScope v0.1.0-rc1 is a local release candidate for validation before the stable v0.1.0 tag. It is not published to PyPI and no remote release is created by this checklist.

### Included

- **LocalScope core**: local-first scanner, task queue, microtask runner, deterministic reducer, and Markdown/JSON reports.
- **CLI `localscope`**: editable install console script, with `python -m governor.main` kept as the compatibility path.
- **Core flow commands**: `scan`, `tasks`, `run-tasks`, `audit`, and `report`.
- **JSON Guard**: parse, extract, repair, and validate local model JSON responses.
- **SQLite memory**: reuse task results by project path, file hash, model, prompt version, and task type.
- **Structured JSONL logging**: run/task/error summaries with secret redaction.
- **Model profiles**: operational stats per model/task/profile; no training or fine-tuning.
- **Adaptive limits**: conservative max-chars recommendations from observed model behavior.
- **Prompt manager**: controlled prompt variants and prompt recommendation support.
- **Benchmarking**: `benchmark-models`, `benchmark-profile`, and `calibrate-models`.
- **Model recommendations**: filtered recommendations that ignore demo/test models by default.
- **Providers architecture**: Ollama and OpenAI-compatible provider interfaces.
- **MCP tools**: `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`.
- **Adapters**: OpenClaw and OpenCode high-level read-only wrappers.
- **Graphify optional provider**: consumes existing `graphify-out/` context without requiring Graphify.
- **Web UI**: local read-only dashboard for reports, logs, benchmarks, and recommendations.
- **suggest-patch**: read-only patch proposal generation; patches are not applied automatically.

## [0.1.0] — 2025-06-25

### Initial MVP Release

First installable release of LocalScope, a local-first read-only project analysis suite for AI agents and local models.

### Core

- **Scanner**: Walk folders, detect project profiles, compute file hashes.
- **Task queue**: Generate prioritized microtasks from scanner output.
- **Task runner**: Execute microtasks via local models with SQLite memory reuse.
- **Audit**: One-command full flow: scan → tasks → run-tasks → report.
- **Report**: Deterministic Markdown and JSON report generation.
- **Profiles**: Auto-detection for python, javascript, java, php, wordpress, docker, general.
- **Calibration fixtures**: 9 small fixture projects for profile-specific benchmarking.

### Model Analysis

- **Ollama provider**: Native `http://127.0.0.1:11434/api/chat` integration.
- **JSON Guard**: Parse, extract, repair, and validate model responses against JSON Schema.
- **SQLite memory**: Reuse task results by project path, file hash, model, prompt version, and task type.
- **Model profiles**: Operational stats per model/task/profile (success rate, repair rate, avg response ms).
- **Adaptive limits**: Adjust `max_chars_per_file` based on model profile metrics.
- **Prompt manager**: Controlled prompt variants (v1, v2_strict_json, v3_short_schema).
- **Patch suggester**: Generate reviewable patch proposals without applying them.

### Model Providers

- **Extensible provider architecture**: `ModelProvider` ABC with `ProviderResponse` and `ProviderHealth`.
- **Ollama provider**: Wraps existing `ollama_client` module.
- **OpenAI-compatible provider**: Generic endpoint support via environment variables (LM Studio, vLLM, etc.).

### Benchmarking & Recommendations

- **`benchmark-models`**: Compare installed Ollama models on a project fixture.
- **`benchmark-profile`**: Compare models per project type using calibration fixtures.
- **`calibrate-models`**: Warm-up recommendations across profiles.
- **`model-recommendations`**: Recommend best model/prompt/limits with 4 confidence tiers (none→low→medium→high).
- **Model resolver**: Centralized priority: manual override → benchmark → config → default.

### Logging

- **Structured JSONL logging**: Task events, error events, run lifecycle.
- **`logs` commands**: `summary`, `errors --limit`, `tasks --limit`.
- **Secret redaction**: API keys, tokens, passwords redacted automatically.

### Web UI

- **Local read-only dashboard**: View reports, logs, benchmarks, recommendations.
- **Zero external dependencies**: Uses only Python stdlib (`http.server`).
- **Binds `127.0.0.1`** by default, never `0.0.0.0`.

### Adapters

- **OpenClaw adapter**: Wrapper CLI returning JSON.
- **OpenCode adapter**: Wrapper CLI returning JSON.
- **MCP server**: Experimental stdio adapter with 4 tools (`localscope_audit`, `localscope_status`, `localscope_report`, `localscope_graph_info`).

### Context Providers

- **Filesystem scanner**: Always on, no dependencies.
- **Graphify**: Optional structural context provider from `graphify-out/`.

### CLI

- **`localscope` command**: Entry point via `pyproject.toml` console script.
- **`python -m governor.main`**: Compatibility path maintained.
- **25+ subcommands**: audit, scan, tasks, run-tasks, report, ollama-test, graphify-info, model-stats, model-recommendations, prompts, benchmark-models, benchmark-profile, calibrate-models, suggest-patch, logs, webui, providers.

### Security

- **Read-only by default**: Never modifies analyzed files.
- **No `apply_patch`**: Patches are proposed but never applied automatically.
- **No dangerous tools**: `write_file`, `run_command`, `shell`, `exec`, `apply_patch` are forbidden in adapters and MCP.
- **Secret redaction**: Logs redact API keys, tokens, and passwords.
- **Path validation**: Rejects path traversal in Web UI and adapters.
- **Local-only Web UI**: Binds `127.0.0.1` by default.

### Developer Experience

- **Editable install**: `pip install -e .[test]`.
- **338+ tests**: Full pytest suite.
- **AGENTS.md**: Permanent rules for AI agent collaboration.
- **PROJECT_BRIEF.md**: Quick orientation for contributors.
- **RELEASE_MVP.md**: Comprehensive release documentation.
