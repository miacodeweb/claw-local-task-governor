# LocalScope Roadmap

This roadmap starts from the current MVP and the reorientation from Claw Local Task Governor to LocalScope.

**Current release: 0.1.0 MVP** — installable via `pip install -e .` with `localscope` CLI.

## Done In 0.1.0 MVP

- Generic read-only scanner.
- Extensible profiles (9 profiles including calibration fixtures).
- Task queue with scanner and optional Graphify prioritization.
- Ollama native provider.
- JSON Guard with schema validation.
- SQLite memory reuse.
- Deterministic Markdown and JSON reports.
- OpenClaw wrapper CLI.
- OpenClaw adapter documentation with manual command, compatibility shim, prompts, and read-only safety notes.
- OpenCode wrapper CLI.
- Experimental MCP stdio adapter with `localscope_audit`, `localscope_status`, `localscope_report`, and `localscope_graph_info`.
- OpenCode MCP setup documentation and smoke-test guidance.
- Shared adapter contract under `adapters/common/`.
- Optional patch proposal mode that saves diffs without applying them.
- Model benchmark runner (`benchmark-models` command).
- Profile benchmark runner (`benchmark-profile` command).
- Model recommendations with confidence levels (`model-recommendations`).
- Model calibration/warm-up (`calibrate-models`).
- Structured JSONL logging (`logs` commands).
- Centralized model resolver (`--model`, `--use-benchmark-recommendations`).
- Calibration fixture projects (9 profiles, 3-6 files each).
- `localscope` CLI entry point via `pyproject.toml`.
- RELEASE_MVP.md and smoke tests.
- Local read-only Web UI (`localscope webui`).
- Extensible model provider architecture (Ollama + OpenAI-compatible).

## Rebranding And Compatibility

### Phase 1: Documentation And Brand

- Use LocalScope as product/core name.
- Document Claw Local Task Governor as the original MVP name.
- Keep `governor/` as temporary internal package.
- Keep current CLI commands working.

### Phase 2: CLI Alias

- Add a `localscope` CLI entry point while keeping `python -m governor.main`.
- Keep backward compatibility for scripts and tests.

### Phase 3: Internal Structure Optional

- Introduce a `localscope/` package or compatibility facade.
- Move core modules carefully.
- Keep adapter modules separate.

### Phase 4: Package Finalization

- Rename package metadata when tests and docs are ready.
- Keep migration notes for old users.

## Adapter Roadmap

### OpenClaw Adapter

Current status: CLI wrapper implemented and documented. A native OpenClaw plugin/tool definition can be added later using the current wrapper contract.

Rules:

- Keep one high-level tool: `local_scope_audit`.
- Keep `local_project_audit` only as a compatibility alias.
- Keep `read_only=true` mandatory.
- Do not expose low-level file, shell, write, or patch tools.
- Keep LocalScope independent; OpenClaw remains an adapter.

### OpenCode Adapter

Current status: CLI wrapper implemented. MCP setup documentation exists for OpenCode-compatible clients.

Rules:

- Use the same high-level local audit flow.
- Keep read-only behavior by default.
- Do not duplicate core logic inside the adapter.
- Prefer the MCP server when OpenCode can launch external MCP stdio servers.

### MCP Optional

Current status: experimental stdio server implemented under `adapters/mcp/` with one audit tool and three read-only query tools.

Rules:

- Keep tool count small.
- Prefer high-level workflows over low-level operations.
- Preserve read-only defaults.
- Keep `localscope_audit` as the high-level audit tool.
- Keep `localscope_status`, `localscope_report`, and `localscope_graph_info` read-only.
- Do not expose `read_file`, `write_file`, `run_command`, or `apply_patch`.

See [MCP Plan](MCP_PLAN.md).

### Graphify MCP Optional

If Graphify exposes a stable MCP interface later, use it as an optional structural context source.

Graphify must remain optional. The scanner stays the fallback.

## Model And Analysis Roadmap

### Local Model Benchmarking (done)

Compare installed Ollama models deterministically:

- `benchmark-models` command with `--models` and `--all-ollama`.
- Per-model metrics: JSON valid/repair/fail rates, response times, scoring.
- Markdown and JSON reports in `reports/benchmarks/`.
- Dry-run mode (`--dry-run`) to preview without calling Ollama.
- Updates `model_profiles` with benchmark results.
- No model downloads (uses only installed models via `ollama list`).

### Advanced Model Profile Learning

Extend operational model statistics:

- JSON success rate by model and task type.
- Repair rate.
- Timeout rate.
- Recommended task size.
- Prompt version performance.

This is operational learning, not model training.

### Patch Suggestions Without Applying

Improve patch proposal generation:

- Stronger validation that diffs match existing findings.
- Better file path checks.
- Clearer review metadata.

The system should still not apply patches automatically.

### Future Human-Approved Apply Patch

Possible future version:

- Apply patches only after explicit human approval.
- Show exact diff.
- Require project-local path validation.
- Keep rollback guidance.

No automatic editing should be added without a separate safety review.

## Not Planned For MVP

- Fine-tuning local models.
- Vector DB or embeddings.
- Native OpenClaw plugin packaging.
- Native OpenCode plugin packaging beyond MCP/wrapper configuration.
- Full dependency-backed MCP server beyond the current minimal stdio implementation.
- Automatic command execution over analyzed projects.
- Automatic file editing.
