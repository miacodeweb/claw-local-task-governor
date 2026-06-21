# OpenClaw integration

This integration exposes three high-level read-only tools for OpenClaw:

```text
local_project_audit
local_audit_status
local_audit_report
```

`local_project_audit` runs the internal governor flow:

```text
scan -> tasks -> run-tasks -> report
```

The status and report tools only read existing governor outputs. They do not run a new audit.

These tools do not expose low-level file tools such as `read_file` or `write_file`, and they do not edit the audited project.

## local_project_audit

```json
{
  "path": "D:/path/to/project",
  "profile": "auto",
  "mode": "general",
  "max_files": 50,
  "read_only": true
}
```

Supported profiles:

```text
auto, general, php, wordpress, javascript, python, java, docker
```

Supported modes:

```text
general, security, code_quality, performance, seo
```

`read_only` must be `true`. If it is `false`, the tool returns a rejected response and does not run the audit.

CLI wrapper:

```bash
python -m governor.main openclaw-audit --path "D:/path/to/project" --profile auto --mode general --max-files 50 --read-only true
```

## local_audit_status

Returns recent audit reports and current task-result status without scanning, queuing, running Ollama, or reducing again.

Arguments:

```json
{
  "output_dir": "reports",
  "limit": 5
}
```

CLI wrapper:

```bash
python -m governor.main openclaw-status --output-dir reports --limit 5
```

Response shape:

```json
{
  "status": "completed",
  "output_dir": "D:/claw-local-task-governor/reports",
  "audits_count": 1,
  "recent_audits": [
    {
      "status": "completed",
      "report_path": "D:/claw-local-task-governor/reports/audit-20260621-153045.md",
      "json_report_path": "D:/claw-local-task-governor/reports/audit-20260621-153045.json",
      "summary": "Audit reduced 5 analyzed files with 1 actionable findings, 0 reused results, and 0 JSON failures.",
      "files_analyzed": 5,
      "json_failed": 0,
      "updated_at": 1782055845.0
    }
  ],
  "current_task_results": {
    "project_path": "D:/path/to/project",
    "generated_at": "2026-06-21T15:30:45+00:00",
    "tasks_selected": 5,
    "tasks_completed": 5,
    "tasks_failed": 0,
    "tasks_reused": 0
  }
}
```

## local_audit_report

Returns a compact summary from an existing final report. Pass either the JSON report path or the Markdown report path. If a Markdown path is given, the tool reads the matching `.json` report.

Arguments:

```json
{
  "report_path": "D:/claw-local-task-governor/reports/audit-20260621-153045.json"
}
```

CLI wrapper:

```bash
python -m governor.main openclaw-report --report-path "D:/claw-local-task-governor/reports/audit-20260621-153045.json"
```

Response shape:

```json
{
  "status": "completed",
  "report_path": "D:/claw-local-task-governor/reports/audit-20260621-153045.md",
  "json_report_path": "D:/claw-local-task-governor/reports/audit-20260621-153045.json",
  "summary": "Audit reduced 5 analyzed files with 1 actionable findings, 0 reused results, and 0 JSON failures.",
  "profile_detected": "python",
  "files_scanned": 120,
  "files_analyzed": 5,
  "files_reused_from_memory": 0,
  "json_valid": 5,
  "json_repaired": 0,
  "json_failed": 0,
  "findings_by_priority": {
    "critical": 0,
    "high": 0,
    "medium": 1,
    "low": 0,
    "none": 4
  },
  "failed_tasks": 0,
  "recommendations": []
}
```

## Safety

- `local_project_audit` only calls existing read-only governor steps.
- `local_audit_status` and `local_audit_report` only read existing governor output files.
- The tools do not modify files inside the audited project.
- The tools do not expose separate read, write, shell, or edit tools.
