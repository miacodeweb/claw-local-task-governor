# Contributing to LocalScope

## Setup

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[test]
Copy-Item config.example.yaml config.yaml
```

## Running Tests

```powershell
# Single file
pytest tests/test_main.py

# Single test
pytest tests/test_main.py::test_scan_command_passes_forced_profile

# Full suite
pytest --basetemp="$env:TEMP\pytest-tmp"
```

Use `--basetemp` if `pytest-of-crist` has permission issues on Windows.

## Security Rules

- Follow read-only defaults.
- Never add `apply_patch`, `write_file`, `run_command`, `shell`, or `exec` tools.
- Keep adapter/MCP stdout JSON clean — logs go to stderr or JSONL files.
- Do not store API keys in config files — use environment variables.
- Do not commit `logs/`, `reports/`, `data/`, `.env`, or `*.sqlite`.

## Code Conventions

- Match existing import style (`from __future__ import annotations`).
- Use dataclasses for data structures.
- Keep context minimal when working with AI agents — read `PROJECT_BRIEF.md` first.
- List at most 8 files before editing — read only what you need.
- Write tests for new features using mocks — do not depend on Ollama being available.

## Architecture Invariants

- **Graphify is optional** — never make it a hard dependency.
- **OpenClaw and OpenCode are adapters, not core** — keep them outside `governor/`.
- **No fine-tuning** — model profiles track operational stats, never train.
- **No automatic model downloads** — users pull Ollama models manually.
- **No copying Graphify into LocalScope** — consume output only.
- **No generic filesystem tools** in adapters or MCP.
- **No modifying analyzed projects** — only write to `reports/` and `data/`.

## Pull Request Checklist

See `.github/PULL_REQUEST_TEMPLATE.md`.
