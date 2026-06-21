<div align="center">

# Claw Local Task Governor

### A read-only local task governor for safer audits with Ollama, Graphify, and OpenClaw

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![Status](https://img.shields.io/badge/MVP-ready-2EA44F?style=for-the-badge)](#)
[![Mode](https://img.shields.io/badge/Mode-read--only-0A66C2?style=for-the-badge)](#)
[![Tests](https://img.shields.io/badge/Tests-pytest-6F42C1?style=for-the-badge)](#)

**Languages:** [English](#english) · [Español](#español) · [Português do Brasil](#português-do-brasil)

</div>

---

## English

### Overview

Claw Local Task Governor is a generic, read-only orchestration layer for auditing
large local project folders with smaller and safer tasks. It scans a project,
creates microtasks, optionally calls a local Ollama model, validates strict JSON
responses, reuses previous results from SQLite memory, and generates Markdown
and JSON reports.

It is not WordPress-specific. WordPress is only one optional profile among
general, PHP, JavaScript, Python, Java, Docker, and other future profiles.

### What It Does

| Area | MVP capability |
| --- | --- |
| Scanner | Safe generic project scan with hashes and profile detection |
| Task Queue | Small pending microtasks from relevant files |
| Ollama | Native `http://127.0.0.1:11434/api/chat` client |
| JSON Guard | Extracts, repairs, and validates JSON model output |
| Memory | SQLite reuse by file hash, model, and prompt version |
| Reports | Deterministic Markdown and JSON audit reports |
| Graphify | Optional enrichment if `graphify-out/graph.json` exists |
| OpenClaw | High-level CLI wrapper tools |
| Patch Suggestions | Reviewable `.diff` proposals, never applied automatically |

### Safety Model

- Read-only by default.
- The audited project is not modified.
- Governor outputs are written under `reports/` and `data/`.
- Patch suggestions are saved to `reports/patches/` and are not applied.
- OpenClaw wrappers do not expose `read_file`, `write_file`, shell, or edit tools.
- Heavy folders like `.git`, `node_modules`, `vendor`, caches, and build outputs
  are ignored by default.

### Requirements

- Python 3.10+
- Windows 10, WSL, or Linux
- Ollama for model-backed analysis
- OpenClaw if you want agent integration
- Graphify only if you want optional graph enrichment

### Installation

Windows PowerShell:

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
```

WSL/Linux:

```bash
cd /path/to/claw-local-task-governor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Ollama setup:

```bash
ollama pull qwen2.5-coder:7b
cp config.example.yaml config.yaml
python -m governor.main ollama-test
```

### Main Workflow

```bash
# 1. Scan a project
python -m governor.main scan /path/to/project

# 2. Build the task queue
python -m governor.main tasks /path/to/project

# 3. Check Ollama
python -m governor.main ollama-test

# 4. Run a limited batch
python -m governor.main run-tasks /path/to/project --max-tasks 5

# 5. Generate final reports
python -m governor.main report /path/to/project
```

Generated files:

```text
reports/scan_result.json
reports/tasks.json
reports/task_results.json
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
data/memory.sqlite
```

### OpenClaw Usage

Use one high-level audit tool:

```bash
python -m governor.main openclaw-audit --path "D:/path/to/project" --profile auto --mode general --max-files 50 --read-only true
```

Check recent audit status:

```bash
python -m governor.main openclaw-status --output-dir reports --limit 5
```

Read an existing report summary:

```bash
python -m governor.main openclaw-report --report-path reports/audit-YYYYMMDD-HHMMSS.json
```

See [`openclaw/README_OPENCLAW.md`](openclaw/README_OPENCLAW.md) and
[`openclaw/tool_manifest.json`](openclaw/tool_manifest.json).

### Graphify

Graphify is optional. The governor does not run Graphify automatically. If the
audited project already contains:

```text
graphify-out/graph.json
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
```

the task queue can use graph signals to improve prioritization. If Graphify is
missing, the scanner-only workflow still works.

### Patch Suggestions

```bash
python -m governor.main suggest-patch /path/to/project --report-path reports/audit-YYYYMMDD-HHMMSS.json --max-findings 5
```

Patch proposals are saved as:

```text
reports/patches/*.diff
```

Every file includes:

```text
Propuesta no aplicada automaticamente.
```

The patch is for review only. The governor validates that the diff refers to the
expected file and stays inside the project, but it never applies the change.

### Example Report

```markdown
# Claw Local Task Governor Audit

## Resumen ejecutivo
Audit reduced 5 analyzed files with 1 actionable findings, 0 reused results, and 0 JSON failures.

## Metricas
- Perfil detectado: python
- Archivos escaneados: 120
- Archivos analizados: 5
- JSON validos: 5
- JSON reparados: 0
- JSON fallidos: 0

## Hallazgos por prioridad
### high
- src/app.py:42 [security]: Unsafe input handling. Recomendacion: Validate inputs.
```

### Troubleshooting

| Problem | What to try |
| --- | --- |
| Ollama does not respond | Run `ollama list` and `python -m governor.main ollama-test` |
| Model not found | Run `ollama pull qwen2.5-coder:7b` or change `config.yaml` |
| Invalid JSON | Lower `max_chars_per_file`, run fewer tasks, or use a stronger local model |
| Graphify not detected | Make sure `graphify-out/graph.json` exists in the audited project |
| Folder permissions | Ensure the governor can read the project and write to `reports/` and `data/` |

### Tests

```bash
pytest
```

---

## Español

### Resumen

Claw Local Task Governor es una capa local, genérica y de solo lectura para
auditar carpetas grandes de proyectos usando tareas pequeñas y seguras. Escanea
el proyecto, crea microtareas, puede llamar a un modelo local mediante Ollama,
valida respuestas JSON estrictas, reutiliza resultados con memoria SQLite y
genera reportes Markdown y JSON.

No es un sistema exclusivo para WordPress. WordPress es solo un perfil opcional,
igual que PHP, JavaScript, Python, Java, Docker y perfiles futuros

### Capacidades del MVP

| Área | Capacidad |
| --- | --- |
| Scanner | Escaneo genérico seguro con hashes y detección de perfil |
| Cola de tareas | Microtareas pendientes desde archivos relevantes |
| Ollama | Cliente nativo para `http://127.0.0.1:11434/api/chat` |
| JSON Guard | Extrae, repara y valida JSON del modelo |
| Memoria | Reutilización SQLite por hash, modelo y versión de prompt |
| Reportes | Reportes determinísticos Markdown y JSON |
| Graphify | Enriquecimiento opcional si existe `graphify-out/graph.json` |
| OpenClaw | Herramientas wrapper CLI de alto nivel |
| Parches sugeridos | Propuestas `.diff` revisables, nunca aplicadas automáticamente |

### Modelo de seguridad

- Solo lectura por defecto.
- El proyecto auditado no se modifica.
- Las salidas del gobernador se escriben en `reports/` y `data/`.
- Las propuestas de parche se guardan en `reports/patches/` y no se aplican.
- Los wrappers de OpenClaw no exponen `read_file`, `write_file`, shell ni edición.
- Carpetas pesadas como `.git`, `node_modules`, `vendor`, cachés y builds se
  ignoran por defecto.

### Requisitos

- Python 3.10+
- Windows 10, WSL o Linux
- Ollama para análisis con modelo local
- OpenClaw si querés integración con agente
- Graphify solo si querés enriquecimiento opcional con grafo

### Instalación

Windows PowerShell:

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
```

WSL/Linux:

```bash
cd /path/to/claw-local-task-governor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Configurar Ollama:

```bash
ollama pull qwen2.5-coder:7b
cp config.example.yaml config.yaml
python -m governor.main ollama-test
```

### Flujo principal

```bash
# 1. Escanear proyecto
python -m governor.main scan /path/to/project

# 2. Crear cola de tareas
python -m governor.main tasks /path/to/project

# 3. Probar Ollama
python -m governor.main ollama-test

# 4. Ejecutar un lote limitado
python -m governor.main run-tasks /path/to/project --max-tasks 5

# 5. Generar reportes finales
python -m governor.main report /path/to/project
```

Archivos generados:

```text
reports/scan_result.json
reports/tasks.json
reports/task_results.json
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
data/memory.sqlite
```

### Uso con OpenClaw

Ejecutar auditoría:

```bash
python -m governor.main openclaw-audit --path "D:/path/to/project" --profile auto --mode general --max-files 50 --read-only true
```

Consultar estado:

```bash
python -m governor.main openclaw-status --output-dir reports --limit 5
```

Leer resumen de reporte:

```bash
python -m governor.main openclaw-report --report-path reports/audit-YYYYMMDD-HHMMSS.json
```

### Graphify

Graphify es opcional. El gobernador no lo ejecuta automáticamente. Si el
proyecto auditado ya contiene `graphify-out/graph.json`, la cola puede usar esas
señales para mejorar la prioridad de tareas. Si no existe, el flujo con scanner
propio sigue funcionando.

### Propuestas de parche

```bash
python -m governor.main suggest-patch /path/to/project --report-path reports/audit-YYYYMMDD-HHMMSS.json --max-findings 5
```

Los diffs se guardan en:

```text
reports/patches/*.diff
```

Son solo propuestas revisables. No se aplican cambios automáticamente.

### Troubleshooting

| Problema | Qué probar |
| --- | --- |
| Ollama no responde | Ejecutar `ollama list` y `python -m governor.main ollama-test` |
| Modelo no encontrado | Ejecutar `ollama pull qwen2.5-coder:7b` o cambiar `config.yaml` |
| JSON inválido | Reducir `max_chars_per_file`, ejecutar menos tareas o usar un modelo más fuerte |
| Graphify no detectado | Confirmar que exista `graphify-out/graph.json` |
| Permisos de carpeta | Confirmar lectura del proyecto y escritura en `reports/` y `data/` |

---

## Português do Brasil

### Visão geral

Claw Local Task Governor é uma camada local, genérica e somente leitura para
auditar pastas grandes de projetos usando tarefas menores e mais seguras. Ele
escaneia o projeto, cria microtarefas, pode chamar um modelo local via Ollama,
valida respostas JSON estritas, reutiliza resultados com memória SQLite e gera
relatórios Markdown e JSON.

Não é uma ferramenta exclusiva para WordPress. WordPress é apenas um perfil
opcional, junto com PHP, JavaScript, Python, Java, Docker e perfis futuros.

### Capacidades do MVP

| Área | Capacidade |
| --- | --- |
| Scanner | Escaneamento genérico seguro com hashes e detecção de perfil |
| Fila de tarefas | Microtarefas pendentes a partir de arquivos relevantes |
| Ollama | Cliente nativo para `http://127.0.0.1:11434/api/chat` |
| JSON Guard | Extrai, repara e valida JSON gerado pelo modelo |
| Memória | Reutilização SQLite por hash, modelo e versão de prompt |
| Relatórios | Relatórios determinísticos em Markdown e JSON |
| Graphify | Enriquecimento opcional se existir `graphify-out/graph.json` |
| OpenClaw | Ferramentas wrapper CLI de alto nível |
| Sugestões de patch | Propostas `.diff` revisáveis, nunca aplicadas automaticamente |

### Modelo de segurança

- Somente leitura por padrão.
- O projeto auditado não é modificado.
- As saídas do governador são gravadas em `reports/` e `data/`.
- Sugestões de patch são salvas em `reports/patches/` e não são aplicadas.
- Os wrappers do OpenClaw não expõem `read_file`, `write_file`, shell ou edição.
- Pastas pesadas como `.git`, `node_modules`, `vendor`, caches e builds são
  ignoradas por padrão.

### Requisitos

- Python 3.10+
- Windows 10, WSL ou Linux
- Ollama para análise com modelo local
- OpenClaw se você quiser integração com agente
- Graphify apenas se quiser enriquecimento opcional com grafo

### Instalação

Windows PowerShell:

```powershell
cd D:\claw-local-task-governor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
```

WSL/Linux:

```bash
cd /path/to/claw-local-task-governor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Configurar Ollama:

```bash
ollama pull qwen2.5-coder:7b
cp config.example.yaml config.yaml
python -m governor.main ollama-test
```

### Fluxo principal

```bash
# 1. Escanear projeto
python -m governor.main scan /path/to/project

# 2. Criar fila de tarefas
python -m governor.main tasks /path/to/project

# 3. Testar Ollama
python -m governor.main ollama-test

# 4. Executar um lote limitado
python -m governor.main run-tasks /path/to/project --max-tasks 5

# 5. Gerar relatórios finais
python -m governor.main report /path/to/project
```

Arquivos gerados:

```text
reports/scan_result.json
reports/tasks.json
reports/task_results.json
reports/audit-YYYYMMDD-HHMMSS.md
reports/audit-YYYYMMDD-HHMMSS.json
data/memory.sqlite
```

### Uso com OpenClaw

Executar auditoria:

```bash
python -m governor.main openclaw-audit --path "D:/path/to/project" --profile auto --mode general --max-files 50 --read-only true
```

Consultar status:

```bash
python -m governor.main openclaw-status --output-dir reports --limit 5
```

Ler resumo de relatório:

```bash
python -m governor.main openclaw-report --report-path reports/audit-YYYYMMDD-HHMMSS.json
```

### Graphify

Graphify é opcional. O governador não executa Graphify automaticamente. Se o
projeto auditado já tiver `graphify-out/graph.json`, a fila pode usar esses
sinais para melhorar a prioridade das tarefas. Se não existir, o fluxo com o
scanner próprio continua funcionando.

### Sugestões de patch

```bash
python -m governor.main suggest-patch /path/to/project --report-path reports/audit-YYYYMMDD-HHMMSS.json --max-findings 5
```

Os diffs são salvos em:

```text
reports/patches/*.diff
```

São apenas propostas revisáveis. Nenhuma alteração é aplicada automaticamente.

### Solução de problemas

| Problema | O que tentar |
| --- | --- |
| Ollama não responde | Executar `ollama list` e `python -m governor.main ollama-test` |
| Modelo não encontrado | Executar `ollama pull qwen2.5-coder:7b` ou alterar `config.yaml` |
| JSON inválido | Reduzir `max_chars_per_file`, executar menos tarefas ou usar um modelo mais forte |
| Graphify não detectado | Confirmar que `graphify-out/graph.json` existe |
| Permissões de pasta | Confirmar leitura do projeto e escrita em `reports/` e `data/` |

---

## License

Add your preferred license before publishing publicly.
