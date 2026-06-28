# Windows 10 + WSL + Ollama

This guide focuses on running LocalScope on Windows 10, PowerShell, WSL, and Ollama.

## Windows PowerShell Setup

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
Copy-Item config.example.yaml config.yaml
```

The repository path may still use the old MVP folder name. The current product name is LocalScope.

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## WSL Setup

From WSL:

```bash
cd /mnt/d/claw-local-task-governor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
cp config.example.yaml config.yaml
```

Windows paths become WSL paths:

```text
D:\ruta\al\proyecto
/mnt/d/ruta/al/proyecto
```

## Ollama

Ollama is the first local model provider supported by LocalScope.

```powershell
ollama list
ollama pull qwen2.5-coder:7b
python -m governor.main ollama-test
```

If `ollama-test` fails:

- Confirm Ollama is running.
- Run `ollama serve` if needed.
- Check `config.yaml`.
- Confirm the configured model appears in `ollama list`.

## Paths With Spaces

Always quote paths with spaces:

```powershell
python -m governor.main scan "D:\Mis Proyectos\App Demo"
python -m governor.main audit "D:\Mis Proyectos\App Demo" --profile auto --max-tasks 5
python -m adapters.openclaw.local_scope_audit --path "D:\Mis Proyectos\App Demo" --max-tasks 5
python -m adapters.opencode.local_scope_audit --path "D:\Mis Proyectos\App Demo" --max-tasks 5
```

## PowerShell And UTF-8 BOM

Some Windows tools create JSON files with UTF-8 BOM. The task runner reads `tasks.json` using `utf-8-sig`, so BOM is tolerated there.

For manually edited files, prefer UTF-8 without BOM when possible.

## Windows And WSL Permissions

If a project lives in Windows and LocalScope runs inside WSL:

- Use `/mnt/d/...` paths.
- Ensure WSL can read the project folder.
- Ensure the repository folder can write `reports/` and `data/`.
- Avoid mixing Windows and WSL virtual environments.

## Adapter Notes

- OpenClaw adapter: `adapters/openclaw/local_scope_audit.py`.
- OpenCode adapter: `adapters/opencode/local_scope_audit.py`.
- MCP: future integration, not implemented yet.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Ollama no responde | Run `ollama list`, then `ollama serve`, then `python -m governor.main ollama-test`. |
| Modelo no encontrado | Run `ollama pull qwen2.5-coder:7b` or update `config.yaml`. |
| JSON invalido | Reduce `max_chars_per_file`, use fewer tasks, or use a stronger model. |
| Graphify no detectado | Run `python -m governor.main graphify-info <path>` and check `graphify-out/graph.json`. |
| Path con espacios | Quote the path. |
| Permisos WSL/Windows | Verify read access to the target and write access to `reports/` and `data/`. |
