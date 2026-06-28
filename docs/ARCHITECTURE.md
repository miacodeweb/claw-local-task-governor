# LocalScope Architecture

LocalScope is a local-first analysis suite for folders, code projects, configuration trees, documentation, and mixed file structures.

The original MVP name was Claw Local Task Governor. The current product/core identity is LocalScope.

## Conceptual Layers

```text
Adapters
  -> OpenClaw wrapper
  -> OpenCode wrapper
  -> MCP stdio adapter (experimental)

LocalScope core
  -> scanner
  -> profiles
  -> optional Graphify context provider
  -> model providers (Ollama, OpenAI-compatible)
  -> task queue / prioritizer
  -> microtask runner
  -> Ollama provider
  -> JSON Guard
  -> SQLite memory
  -> deterministic reports

Benchmark & recommendations (built on core)
  -> model benchmark (per-project fixture)
  -> profile benchmark (per-project-type calibration fixtures)
  -> model recommendations (confidence levels, prompt/max_chars suggestions)
  -> calibration/warm-up (controlled multi-profile benchmark)
```

## Temporary Internal Package

The internal Python module is still named:

```text
governor/
```

This stays temporarily to avoid breaking tests, imports, and CLI commands. A future package migration can introduce a `localscope` package or CLI alias in phases.

## Core Principles

- Local-first.
- Read-only by default.
- Centralized safety validation for adapter inputs.
- Generic core, not OpenClaw-only and not WordPress-only.
- Small tasks instead of full-project prompts.
- Strict JSON contracts validated by JSON Schema.
- Deterministic reports.
- Optional integrations, never mandatory.
- Adapters are outside the core concept.

## Core Capabilities

- Local filesystem scanner.
- Task queue.
- Microtask runner.
- Ollama provider.
- JSON Guard.
- SQLite memory.
- Deterministic reports.
- Graphify optional context provider.
- Read-only by default.
- Adapter architecture.

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

## Scanner

The scanner walks a folder safely, ignores heavy or irrelevant folders, computes hashes for relevant files, detects a project profile, and writes:

```text
reports/scan_result.json
```

It does not modify analyzed files.

## Profiles

Profiles live under:

```text
profiles/
governor/profiles/
```

Initial profiles:

```text
general, php, wordpress, javascript, python, java, docker
```

Each profile can define relevant extensions, important files, additional ignored folders, risk patterns, a recommended prompt, and base priority.

## Graphify Context Provider

Graphify is optional. LocalScope only reads existing Graphify output:

```text
graphify-out/graph.json
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
```

If the graph is missing, invalid, or partially recognized, the scanner-only flow continues.

## Task Queue And Prioritizer

The task queue converts `scan_result.json` into small pending tasks in:

```text
reports/tasks.json
```

Priority combines scanner signals and optional Graphify signals. Graphify never replaces the scanner.

## Ollama Provider

The Ollama provider uses the native endpoint:

```text
http://127.0.0.1:11434/api/chat
```

Ollama is the first local model provider. Future providers can be added behind the same model-provider concept.

## JSON Guard

JSON Guard parses model responses, extracts JSON from surrounding text, removes markdown fences, repairs simple trailing commas, and validates against schemas.

Invalid responses do not crash the full run. The task is marked as failed JSON and execution continues.

## SQLite Memory

Memory is stored at:

```text
data/memory.sqlite
```

Results are reused when project path, file path, file hash, model, prompt version, and task type match.

## Reports

The deterministic reducer writes:

```text
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
```

No model is used to write the final report in the MVP.

## Adapters

### OpenClaw

Current integration:

```text
python -m adapters.openclaw.local_scope_audit
python adapters/openclaw/local_scope_audit.py
openclaw/local_project_audit.py
```

It exposes one high-level read-only wrapper and does not expose low-level read, write, shell, or patch tools. OpenClaw should parse the adapter stdout as JSON and use the generated Markdown/JSON reports instead of receiving many LocalScope internals as separate tools.

OpenClaw is not a dependency of the LocalScope core.

### OpenCode

Current integration:

```text
python -m adapters.opencode.local_scope_audit
```

It uses the same shared adapter contract as OpenClaw and does not expose low-level read, write, shell, or patch tools.

### MCP

MCP is an experimental integration option implemented under:

```text
adapters/mcp/server.py
```

Start command:

```text
python -m adapters.mcp.server
```

The current MCP surface exposes:

```text
localscope_audit
localscope_status
localscope_report
localscope_graph_info
```

`localscope_audit` can run the full audit flow. The other tools only query existing status, report, or Graphify outputs.

It must not expose generic `read_file`, `write_file`, `run_command`, `apply_patch`, `shell`, or `exec` tools.

MCP and external adapters share safety limits:

- `read_only=false` is rejected.
- `max_tasks` must be between `1` and `100`.
- Project paths are normalized, must exist, must be directories, and must not be filesystem roots.
- `localscope_report` only reads LocalScope-owned `reports/audit-*.json` or `reports/audit-*.md` files.
- Protocol JSON is written to stdout; human/debug logs belong on stderr.

See [MCP Plan](MCP_PLAN.md).
