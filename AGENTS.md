# AGENTS.md — LocalScope Agent Rules

Permanent rules for Codex and other AI agents working on this repository.

## 1. Context discipline

- Use **minimum context**. Do not read files you don't need.
- Before reading anything, consult `PROJECT_BRIEF.md` for project orientation.

## 2. Read guard

- Do NOT read the entire project unless explicitly ordered.
- Do NOT open these directories:
  - `reports/`
  - `data/`
  - `.git/`
  - `.venv/`
  - `__pycache__/`
  - `.pytest_cache/`
  - `node_modules/`
  - `vendor/`

## 3. Response discipline

- Do NOT paste entire files into responses.
- Keep answers short and focused.

## 4. Before editing a file

- List at most **8 files** you need to read/modify and why.
- Read only those files.
- Match existing code conventions (imports, types, naming, style).

## 5. Testing

- For small changes, run **only the relevant test file or test function**.
- Run `pytest` (full suite) **only at the end of a large block of work**.
- Never run `pytest` as the first or only verification step for a single-line change.

## 6. Safety — DO NOT implement

- `apply_patch` — patches are proposed, never applied automatically
- `write_file` tool for analyzed targets
- `run_command` / `shell` / `exec` — no arbitrary command execution
- Generic `read_file` in adapters or MCP
- Any tool that modifies analyzed projects

## 7. Adapter rules

- Adapters must output **clean JSON to stdout**.
- Human/debug logs must go to **stderr** (critical for MCP protocol).
- Keep `adapters/common/` as the shared contract.

## 8. Architecture invariants

- **Graphify is optional** — never make it a hard dependency.
- **OpenClaw and OpenCode are adapters, not core** — keep them outside `governor/`.
- **No fine-tuning** — model profiles track stats, never train.
- **No automatic model downloads** — users pull Ollama models manually.
- **No copying Graphify into LocalScope** — consume output only.
- **No generic filesystem tools** in adapters or MCP.
- **No modifying analyzed projects** — only write to `reports/` and `data/`.

## 9. New features

- Do NOT implement new features without explicit order.
- Do NOT implement benchmark functionality yet (deferred).
- The `benchmark-models` command does not exist — do not create it.

## 10. Key paths

```
governor/              — core package (temporary name, will become localscope/)
adapters/              — OpenClaw, OpenCode, MCP wrappers (outside core)
adapters/common/       — shared AuditRequest/AuditResponse/run_audit
reports/               — scan/task/result/report outputs (never read by agent)
data/memory.sqlite     — SQLite reuse store (never read by agent)
profiles/              — per-project-type profiles
docs/                  — ARCHITECTURE.md, ROADMAP.md, MCP_PLAN.md
```

## 11. Quick reference

```powershell
# Full audit
python -m governor.main audit path/to/project --profile auto --max-tasks 5

# Dry run (no model calls)
python -m governor.main audit path/to/project --profile auto --max-tasks 5 --dry-run

# Step-by-step
python -m governor.main scan path/to/project
python -m governor.main tasks path/to/project
python -m governor.main run-tasks path/to/project --max-tasks 5
python -m governor.main report path/to/project

# Testing
pytest tests/test_main.py          # single file
pytest tests/test_main.py::test_X  # single test
pytest                              # full suite (only after large changes)
```
