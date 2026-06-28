# LocalScope v0.1.0-rc1 Test Plan

This plan validates the local release candidate before promoting it to stable v0.1.0. It must not publish packages, push tags, or create a remote release.

## Editable Installation

```powershell
python -m pip install -e .
localscope --help
python -m governor.main --help
```

If Windows cannot find `localscope`, check `python -m site --user-base` and add the matching `Scripts` directory to `PATH`.

## CLI Smoke Tests

```powershell
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope scan tests/fixtures/sample_project
localscope tasks tests/fixtures/sample_project
```

Use dry-run first. Do not run long audits during RC validation unless explicitly approved.

## Provider Smoke Tests

```powershell
localscope providers list
localscope providers health
localscope providers models --provider ollama
```

Do not run `ollama pull`; models must already be installed.

## Benchmark Smoke Tests

```powershell
localscope benchmark-profile python --models qwen2.5-coder:7b --max-tasks 1 --dry-run
localscope calibrate-models --profiles python config_files --models qwen2.5-coder:7b --max-tasks 1 --dry-run
localscope model-recommendations --profile python
```

Real calibration is optional and should use small `--max-tasks` values.

## MCP Smoke Tests

```powershell
python -m adapters.mcp.server --self-test
```

Confirm only high-level read-only tools are exposed: `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`.

## Web UI Smoke Tests

```powershell
localscope webui --help
```

Starting the Web UI is optional. If started, it must bind locally and remain read-only.

## Controlled Dogfooding

```powershell
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope audit D:\poker-holdem-analyzer --profile python --max-tasks 5 --model qwen2.5-coder:7b
```

Use a small external project only. Do not audit large roots such as `C:\`, `D:\`, `Users\`, `Windows\`, or `Program Files\`.

## Logs And Reports Review

```powershell
localscope logs summary
localscope logs errors --limit 30
localscope logs tasks --limit 20
```

Review generated reports only at a summary level. Do not include `reports/`, `logs/`, `data/`, `.env`, or `*.sqlite` in commits.

## Promotion Criteria

Promote rc1 to stable v0.1.0 only when:

- Targeted release tests pass.
- Full pytest suite passes.
- Editable install works.
- `localscope --help` works or PATH instructions are documented.
- Dry-run audit works without model calls.
- A small real audit produces valid JSON results.
- No demo/test model is recommended by default.
- No secrets, logs, reports, SQLite files, or generated artifacts are tracked.
- No adapters expose filesystem or write tools.
