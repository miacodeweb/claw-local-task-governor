# PROJECT CONTEXT FOR CODEX

## Project name

**Claw Local Task Governor**

Working name in Spanish: **Gobernador Local de Tareas para OpenClaw**.

This file is intended to be given to Codex as the main project context before starting development.

---

## User environment

The user already has the following installed on a Windows 10 PC:

- Windows 10
- WSL
- Docker
- Ollama for local models
- OpenClaw installed locally
- Graphify installed
- Local low-resource models available through Ollama

The project must be designed first for local development on Windows/WSL, but the code should be portable enough to run later on Linux servers.

---

## Core problem

Local low-resource models often fail when used with agent systems such as OpenClaw because they receive too much context, too many tools, too many files, or complex tool schemas. Typical failures include:

- Invalid JSON output
- Tool calls returned as plain text
- Mixed explanation + JSON
- Hallucinated tool names
- Missing required JSON fields
- Saturation when analyzing large projects
- Failure when asked to inspect thousands of files at once
- Poor reliability when many tools are exposed simultaneously

The goal is not to make local models magically as capable as large cloud models. The goal is to make the work smaller, safer, validated, resumable, and easier for local models to complete.

---

## Main project goal

Create a local orchestration layer for **OpenClaw** that helps local Ollama models work more reliably on large folders and code projects.

The system must:

1. Take a large user request from OpenClaw.
2. Break it into smaller deterministic tasks.
3. Use Graphify as a project map / knowledge graph when available.
4. Select small pieces of relevant context instead of sending the full project to the model.
5. Ask the local model for strict JSON output.
6. Validate and repair JSON when possible.
7. Save task results in local memory.
8. Reuse previous results when files have not changed.
9. Produce Markdown and JSON reports.
10. Return a concise final result back to OpenClaw.

The first version must be **read-only**.

---

## Very important design correction

The project must **not** be WordPress-only.

WordPress was only an example of a large project with many files. The correct design is:

```text
Claw Local Task Governor = generic local task orchestration engine for OpenClaw
WordPress = optional future profile
PHP = optional future profile
JavaScript/Node = optional future profile
Python = optional future profile
Java = optional future profile
Docker/Linux/server config = optional future profile
```

The core must be generic.

---

## High-level architecture

```text
OpenClaw
  ↓
Claw Local Task Governor
  ↓
Graphify adapter          SQLite memory
  ↓                       ↑
Task planner / queue  →  task results
  ↓
Ollama local model
  ↓
JSON Guard
  ↓
Reducer / reporter
  ↓
OpenClaw final summary
```

---

## What Graphify is used for

Graphify should be treated as a **project map / structural memory layer**.

Graphify can generate outputs such as:

- `graphify-out/graph.json`
- `graphify-out/graph.html`
- `GRAPH_REPORT.md`
- cache files

In this project, Graphify is not the entire solution. It complements the Task Governor.

Graphify helps with:

- Understanding project structure
- Discovering important files or nodes
- Finding relationships between files, classes, functions, docs, and modules
- Reducing the need to scan everything manually
- Providing useful context before task planning

The Task Governor still handles:

- Microtask creation
- JSON validation
- JSON repair
- Memory of task results
- Model failure tracking
- Incremental analysis
- Final report generation
- Safety rules
- OpenClaw integration

---

## Core components

### 1. Scanner

Generic fallback scanner used when Graphify is not available or when extra file metadata is needed.

Responsibilities:

- Walk a folder safely
- Detect project type
- Count files
- Ignore irrelevant folders/files
- Calculate SHA256 file hashes
- Identify relevant source/config files
- Create a `scan_result.json`

Must not modify files.

### 2. Graphify adapter

Responsibilities:

- Detect if Graphify output already exists
- Optionally run Graphify if configured and allowed
- Load `graphify-out/graph.json`
- Extract important nodes/files
- Provide structured context to the task planner
- Fall back to the scanner if graph data is unavailable

Initial implementation can be simple:

- Load graph JSON if it exists
- Extract node IDs, paths, labels, and relationships if available
- Return a normalized list of candidate files or project entities

Do not overcomplicate this in the first version.

### 3. Task planner

Responsibilities:

- Convert project information into small tasks
- Prioritize tasks
- Avoid sending too much content to the model
- Track pending/running/completed/failed tasks

Example task:

```json
{
  "task_id": "task-0001",
  "type": "inspect_file",
  "path": "src/main.py",
  "priority": "medium",
  "reason": "source code file detected by project scanner",
  "status": "pending"
}
```

### 4. Ollama client

Responsibilities:

- Connect to Ollama native API
- Prefer `http://127.0.0.1:11434/api/chat`
- Avoid relying on `/v1` for the first implementation
- Send small prompts
- Use low temperature
- Return raw model output

Initial config:

```yaml
ollama:
  base_url: "http://127.0.0.1:11434"
  model: "qwen2.5-coder:7b"
  temperature: 0.1
  timeout_seconds: 120
```

The model must be configurable. Do not hardcode one model.

### 5. JSON Guard

Responsibilities:

- Parse JSON from model responses
- Reject invalid structures
- Extract JSON if surrounded by text
- Remove markdown fences if needed
- Repair simple JSON errors when safe
- Retry once with a repair prompt if needed
- Mark failed tasks instead of crashing the whole audit

Errors to handle:

- Text before/after JSON
- Markdown fenced code blocks
- Trailing commas
- Missing fields
- Invalid enum values
- Incorrect types
- Extra fields
- Empty response

### 6. Memory

Use SQLite for local memory.

Responsibilities:

- Store projects
- Store scanned files and hashes
- Store task results
- Store model behavior profile
- Reuse previous results when file hash has not changed
- Track JSON failures per model and task type

This is not fine-tuning. The model itself does not learn. The system learns operationally how to work better with that model.

### 7. Reducer

Responsibilities:

- Combine task results
- Group findings by risk/severity
- Remove duplicates
- Produce final Markdown and JSON reports
- Summarize reused memory vs newly analyzed files

### 8. OpenClaw integration

Initial integration should expose very few high-level tools to OpenClaw.

Do not expose dozens of low-level tools.

Initial tool idea:

```text
local_project_audit
```

Arguments:

```json
{
  "path": "/path/to/project",
  "profile": "auto|general|wordpress|php|javascript|python|java|docker",
  "mode": "general|security|code_quality|performance|seo",
  "max_files": 50,
  "read_only": true
}
```

Response:

```json
{
  "status": "completed",
  "profile_detected": "python",
  "mode": "general",
  "report_path": "reports/audit-001.md",
  "files_scanned": 120,
  "files_analyzed": 20,
  "files_reused_from_memory": 0,
  "summary": "Audit completed with 3 medium findings and 8 low findings."
}
```

Future tools:

```text
audit_status
audit_report
```

---

## Safety rules

The first version is read-only.

Hard rules:

- Do not delete files.
- Do not modify files.
- Do not execute destructive commands.
- Do not run arbitrary shell commands without explicit user approval.
- Do not leave the requested workspace path.
- Do not follow symlinks outside the workspace.
- Do not expose secrets in reports.
- Do not read full `.env` or credential files into the model without redaction.
- Do not send large binary/image/video files to the model.
- Do not scan `node_modules`, `.git`, build outputs, caches, or vendor directories unless explicitly allowed.

Secret redaction patterns should include:

- API keys
- passwords
- database credentials
- tokens
- private keys
- WordPress salts
- `.env` values

---

## Profiles

The core must support profiles, but profiles should be optional and extensible.

Initial profiles:

```text
general
```

Future profiles:

```text
wordpress
php
javascript
python
java
docker
linux_server
```

The first MVP should not require all profiles to be implemented.

---

## Project type detection

Generic detection rules:

```text
wp-config.php + wp-content/       → wordpress
composer.json                     → php
package.json                      → javascript/node
pyproject.toml or requirements.txt→ python
pom.xml or build.gradle           → java
Dockerfile or docker-compose.yml  → docker
.htaccess                         → apache/web
nginx.conf                        → nginx/web
```

If multiple signals exist, return a ranked list or best match with confidence.

---

## Generic ignore rules

Ignore by default:

```text
.git/
node_modules/
vendor/
dist/
build/
.cache/
cache/
coverage/
.tmp/
tmp/
logs/
__pycache__/
.venv/
venv/
.idea/
.vscode/
wp-content/uploads/
wp-content/cache/
```

Ignore file types:

```text
*.jpg
*.jpeg
*.png
*.gif
*.webp
*.ico
*.svg
*.mp4
*.mov
*.avi
*.zip
*.tar
*.gz
*.7z
*.rar
*.pdf
*.exe
*.dll
*.so
*.bin
*.min.js
*.min.css
*.map
```

These rules can later become configurable.

---

## Relevant file types for initial scanner

Prioritize:

```text
.py
.js
.ts
.jsx
tsx
.php
.java
.cs
.go
.rs
.rb
html
css
json
yaml
yml
toml
xml
md
Dockerfile
docker-compose.yml
package.json
composer.json
pyproject.toml
requirements.txt
pom.xml
build.gradle
.env.example
```

For `.env`, `.env.local`, or files likely to contain secrets, include metadata but redact content.

---

## JSON schema for file analysis

The local model should respond using this minimal JSON contract:

```json
{
  "file": "string",
  "status": "ok|needs_review|error",
  "risk": "none|low|medium|high|critical",
  "summary": "string",
  "findings": [
    {
      "line": null,
      "type": "string",
      "severity": "low|medium|high|critical",
      "evidence": "string",
      "recommendation": "string"
    }
  ],
  "needs_related_file": false,
  "related_files": []
}
```

Rules:

- `findings` must be an array.
- If no finding exists, use `findings: []`.
- Do not invent related files.
- `risk` must reflect the highest severity finding.
- `line` may be `null` if unknown.
- Maximum 5 findings per file in MVP.

---

## Prompt template for local model

Use this as initial prompt for file analysis:

```text
You are analyzing one file from a local code project.

Task:
Analyze the file for obvious problems, risks, code quality issues, security concerns, or suspicious patterns.

Rules:
- Analyze only the provided file content.
- Do not invent files.
- Do not propose editing yet.
- Do not use markdown.
- Do not write explanations outside JSON.
- Return only valid JSON.
- Maximum 5 findings.
- If there are no clear issues, use findings: [].

Required JSON format:
{
  "file": "string",
  "status": "ok|needs_review|error",
  "risk": "none|low|medium|high|critical",
  "summary": "string",
  "findings": [
    {
      "line": number|null,
      "type": "string",
      "severity": "low|medium|high|critical",
      "evidence": "string",
      "recommendation": "string"
    }
  ],
  "needs_related_file": boolean,
  "related_files": []
}

File path:
{{file_path}}

File content:
{{file_content}}
```

---

## Repair prompt for invalid JSON

```text
Your previous response was not valid JSON.

Return only corrected valid JSON.
Do not explain.
Do not use markdown.
Do not add text before or after the JSON.
Use this required schema:

{
  "file": "string",
  "status": "ok|needs_review|error",
  "risk": "none|low|medium|high|critical",
  "summary": "string",
  "findings": [
    {
      "line": number|null,
      "type": "string",
      "severity": "low|medium|high|critical",
      "evidence": "string",
      "recommendation": "string"
    }
  ],
  "needs_related_file": boolean,
  "related_files": []
}

Invalid response:
{{invalid_response}}
```

---

## SQLite schema for MVP

Initial tables:

```sql
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  project_type TEXT,
  created_at TEXT,
  last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  path TEXT NOT NULL,
  hash TEXT NOT NULL,
  size INTEGER,
  extension TEXT,
  importance TEXT,
  last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS task_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  file_path TEXT,
  file_hash TEXT,
  task_type TEXT,
  model TEXT,
  prompt_version TEXT,
  json_valid INTEGER,
  json_repaired INTEGER,
  risk TEXT,
  result_json TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS model_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT,
  task_type TEXT,
  success_count INTEGER DEFAULT 0,
  json_fail_count INTEGER DEFAULT 0,
  json_repair_count INTEGER DEFAULT 0,
  recommended_max_chars INTEGER DEFAULT 12000,
  updated_at TEXT
);
```

---

## Map-reduce strategy

### Map phase

The system analyzes small units:

```text
file → JSON summary
module/folder → aggregated summary
entity/node from Graphify → focused analysis task
```

### Reduce phase

The system combines the JSON summaries:

```text
all task results → grouped findings → final Markdown report + final JSON report
```

### Incremental memory

On later runs:

- Scan files again.
- Compare hashes.
- Reuse previous task results for unchanged files.
- Analyze only changed/new files.
- Regenerate final report from old + new results.

This is how the system regains speed after sacrificing speed for reliability.

---

## Expected repository structure

```text
claw-local-task-governor/
│
├── README.md
├── PROJECT_CONTEXT.md
├── config.example.yaml
├── requirements.txt
├── pyproject.toml
│
├── governor/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── scanner.py
│   ├── profile_detector.py
│   ├── graphify_adapter.py
│   ├── task_queue.py
│   ├── ollama_client.py
│   ├── json_guard.py
│   ├── memory.py
│   ├── reducer.py
│   ├── report_writer.py
│   └── safety.py
│
├── profiles/
│   ├── general/
│   │   ├── rules.yaml
│   │   └── prompt.txt
│   └── wordpress/
│       ├── rules.yaml
│       └── prompt.txt
│
├── schemas/
│   ├── file_analysis.schema.json
│   ├── task.schema.json
│   └── final_report.schema.json
│
├── prompts/
│   ├── inspect_file.txt
│   ├── reduce_findings.txt
│   └── repair_json.txt
│
├── openclaw/
│   ├── README_OPENCLAW.md
│   ├── tool_manifest.json
│   └── plugin_entry.ts
│
├── data/
│   └── .gitkeep
│
├── reports/
│   └── .gitkeep
│
└── tests/
    ├── test_scanner.py
    ├── test_json_guard.py
    ├── test_memory.py
    └── fixtures/
```

---

## Development phases

### Phase 1 — Generic scanner, no AI

Goal:
Create a safe generic scanner.

Tasks:

1. Create repository structure.
2. Implement `scanner.py`.
3. Implement ignore rules.
4. Implement SHA256 hashing.
5. Implement profile detection.
6. Generate `scan_result.json`.
7. Add basic tests.

Expected command:

```bash
python -m governor.main scan /path/to/project
```

Expected output:

```text
Scan completed.
Files found: X
Files ignored: Y
Relevant files: Z
Detected profile: general|python|javascript|wordpress|php|java|docker
Output: reports/scan_result.json
```

### Phase 2 — Ollama + strict JSON

Goal:
Analyze a few files with a local model.

Tasks:

1. Implement `ollama_client.py`.
2. Implement prompt loading.
3. Implement file content truncation.
4. Implement `json_guard.py`.
5. Analyze `--max-files 5` safely.
6. Save raw and parsed results.

Expected command:

```bash
python -m governor.main audit /path/to/project --max-files 5 --model qwen2.5-coder:7b
```

### Phase 3 — SQLite memory

Goal:
Reuse previous results.

Tasks:

1. Implement `memory.py`.
2. Create database tables.
3. Store file hashes and task results.
4. Reuse unchanged file analysis.
5. Show reused vs analyzed count.

### Phase 4 — Map-reduce report

Goal:
Generate a useful report.

Tasks:

1. Implement reducer.
2. Generate Markdown report.
3. Generate final JSON report.
4. Group findings by severity.
5. Include model stats and JSON failures.

### Phase 5 — Graphify adapter

Goal:
Use Graphify output as project map.

Tasks:

1. Detect `graphify-out/graph.json`.
2. Load graph data.
3. Extract candidate files/nodes.
4. Use graph data to prioritize tasks.
5. Fallback to scanner if graph is missing.

### Phase 6 — OpenClaw integration

Goal:
Expose this as a high-level OpenClaw tool.

Tasks:

1. Create `local_project_audit` tool wrapper.
2. Make OpenClaw call the local governor.
3. Return summary + report path.
4. Keep all execution read-only.

---

## What Codex should do first

Start with **Phase 1 only**.

Do not implement all phases at once.

First task for Codex:

```text
Create the initial Python project structure for claw-local-task-governor and implement Phase 1: a generic safe scanner with project profile detection, ignore rules, SHA256 hashing, relevance ranking, and scan_result.json output. Do not use Ollama yet. Do not integrate OpenClaw yet. Do not modify any scanned files.
```

---

## First Codex prompt

Use this prompt after giving Codex this context file:

```text
We are starting Phase 1 of the Claw Local Task Governor project.

Please create the initial repository structure and implement a generic read-only scanner.

Requirements:
1. Python project.
2. CLI command: python -m governor.main scan <path>
3. Recursively scan the target path safely.
4. Do not modify files.
5. Do not follow symlinks outside the target workspace.
6. Ignore common heavy or irrelevant directories and binary/media files.
7. Detect project profile using common markers:
   - wp-config.php + wp-content/ → wordpress
   - composer.json → php
   - package.json → javascript/node
   - pyproject.toml or requirements.txt → python
   - pom.xml or build.gradle → java
   - Dockerfile or docker-compose.yml → docker
8. Calculate SHA256 hash for relevant files.
9. Rank relevant files by basic importance.
10. Generate reports/scan_result.json.
11. Add tests for scanner, profile detection, and ignore rules.
12. Keep the code simple and modular.

Do not implement Ollama, OpenClaw integration, editing, or shell command execution yet.
```

---

## Important implementation preference

Use boring, reliable code.

Avoid overengineering in the first phase.

Prefer:

- `pathlib`
- `hashlib`
- `json`
- `sqlite3` later
- `argparse` or simple CLI first
- `pytest` for tests

Avoid initially:

- LangChain
- complex agent frameworks
- vector databases
- automatic code editing
- broad shell execution
- too many abstractions

---

## Definition of success for Phase 1

Phase 1 is successful when:

1. A folder can be scanned safely.
2. The scanner does not modify anything.
3. The scanner detects probable project type.
4. The scanner ignores heavy folders.
5. The scanner identifies relevant files.
6. The scanner calculates hashes.
7. The scanner creates a useful `scan_result.json`.
8. Tests pass.

---

## Long-term vision

The final project should make OpenClaw more useful with local low-resource models by acting as a stabilizing layer:

```text
Large task → smaller tasks → validated JSON → memory → incremental reports → OpenClaw summary
```

The key philosophy:

```text
Do not make the local model bigger.
Make the task smaller, safer, reusable, and verifiable.
```
