# LocalScope Web UI

Local read-only dashboard for viewing LocalScope reports, logs, benchmarks, and model recommendations.

## Usage

```powershell
localscope webui
```

Opens browser at `http://127.0.0.1:8765`.

Options:
- `--host` — bind host (default `127.0.0.1`)
- `--port` — bind port (default `8765`)
- `--no-browser` — start without opening browser

## Security

- **Read-only** — never modifies files or projects.
- **Local only** — binds to `127.0.0.1` by default, never `0.0.0.0`.
- **No dangerous endpoints** — no `apply_patch`, `write_file`, `run_command`, `shell`, or `exec`.
- **Path sanitized** — rejects path traversal.
- **Only reads LocalScope artifacts** — `reports/`, `logs/`, `benchmarks/`.

## Routes

| Page | Path | Description |
|---|---|---|
| Dashboard | `/` | Overview: report count, benchmarks, logs, recommended model |
| Reports | `/reports` | List audit reports |
| Report detail | `/reports/{id}` | Single report metadata |
| Logs | `/logs` | Log summary |
| Error logs | `/logs/errors` | Recent error entries |
| Task logs | `/logs/tasks` | Recent task entries |
| Benchmarks | `/benchmarks` | List benchmarks |
| Benchmark detail | `/benchmarks/{id}` | Single benchmark detail |
| Model recommendations | `/models/recommendations` | Current model/prompt/limits recommendations |
| Graphify | `/graphify` | Optional Graphify status |

## API (JSON)

| Endpoint | Description |
|---|---|
| `GET /api/status` | Overall status |
| `GET /api/reports` | Report list |
| `GET /api/reports/{id}` | Report detail JSON |
| `GET /api/logs/errors?limit=20` | Error log entries |
| `GET /api/logs/tasks?limit=20` | Task log entries |
| `GET /api/benchmarks` | Benchmark list |
| `GET /api/model-recommendations?profile=python` | Model recommendations |
| `GET /api/graphify` | Graphify status |

## Dependencies

Zero external dependencies — uses only Python stdlib (`http.server`, `json`, `pathlib`).
