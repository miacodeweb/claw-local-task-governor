# Security Policy

## Read-Only By Default

LocalScope is designed to be read-only toward analyzed targets:

- Never modifies analyzed files.
- Never applies patches automatically (`suggest-patch` saves diffs without applying).
- Never executes shell commands over the analyzed project.
- Never exposes `read_file`, `write_file`, `run_command`, `shell`, `exec`, or `apply_patch` as adapter/MCP tools.

## Reporting a Vulnerability

If you discover a security vulnerability in LocalScope, please report it privately:

1. Open a GitHub issue with minimal reproduction steps.
2. Do NOT include real API keys, tokens, or credentials in the report.
3. If the issue is sensitive, email the maintainer directly.

We aim to respond within 48 hours and patch within 7 days for critical issues.

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Security Features

- **Adapter safety**: `read_only=false` is rejected. `max_tasks` bounded 1–100.
- **Project path validation**: Must exist, be directories, not filesystem roots.
- **Secret-like files**: `.env` files are flagged but their content is never included in reports.
- **Log redaction**: API keys, tokens, passwords, and bearer tokens are redacted in JSONL logs.
- **Web UI**: Binds `127.0.0.1` by default, rejects path traversal, read-only endpoints.
- **No credentials in config**: API keys use environment variables (`LOCAL_SCOPE_OPENAI_COMPAT_API_KEY`).

## What LocalScope Does NOT Do

- Does not download models automatically.
- Does not fine-tune or train models.
- Does not modify `config.yaml` automatically.
- Does not send data to remote APIs (all providers are local).
- Does not expose generic filesystem browsing tools.
- Does not include `.env`, `.git`, `node_modules`, or `vendor` in scan reports.
