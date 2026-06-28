# LocalScope

> Local-first project analysis suite for AI agents and local models.

[![Version](https://img.shields.io/badge/version-0.1.0--rc1-blue)](https://github.com/miacodeweb/localscope)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-MVP%20rc1-orange)](#current-status-v010-rc1)

---

## Contents

- [English](#english)
  - [What is LocalScope?](#what-is-localscope)
  - [Why LocalScope exists](#why-localscope-exists)
  - [Problems it solves](#problems-it-solves)
  - [Key features](#key-features)
  - [Architecture overview](#architecture-overview)
  - [Safety model](#safety-model)
  - [Supported targets](#supported-targets)
  - [Integrations](#integrations)
  - [Quick install](#quick-install)
  - [Quick start](#quick-start)
  - [Model benchmarking](#model-benchmarking)
  - [Web UI](#web-ui)
  - [MCP / OpenCode / OpenClaw](#mcp--opencode--openclaw)
  - [Graphify (optional)](#graphify-optional)
  - [Logs and troubleshooting](#logs-and-troubleshooting)
  - [Current status: v0.1.0-rc1](#current-status-v010-rc1)
  - [Roadmap](#roadmap)
  - [Documentation](#documentation)
- [Español](#español)
- [Português](#português)

---

## English

### What is LocalScope?

**LocalScope** helps local AI models work reliably on real projects by splitting large codebases into small read-only tasks, validating model outputs, tracking model performance, and generating structured reports for agents and developers.

It is a local-first, read-only project and folder analysis suite. It scans projects, creates microtasks, uses local models through Ollama or OpenAI-compatible providers, validates every response with JSON Guard, stores reusable memory in SQLite, optionally consumes Graphify knowledge graphs, and generates deterministic Markdown/JSON reports.

> The original MVP internal name was **Claw Local Task Governor**. The current product/core concept is **LocalScope**. The internal Python package is still `governor/` for compatibility (eventual rename to `localscope/`).

### Why LocalScope exists

Local models often fail when used with AI agents on large projects because:

| Problem | Impact |
|---|---|
| Models receive too much context | Truncated inputs, hallucinated outputs, lost details |
| Tasks are too large for small models | Incomplete or invalid responses |
| JSON outputs are unstable | Parsing breaks, agents crash |
| No memory across runs | Redundant work, inconsistent results |
| No visibility into model quality | Hard to pick the right model for a task |
| No safe read-only mode | Risk of unwanted file modifications |

**LocalScope addresses every one of these problems** by breaking work into small validated microtasks, reusing results, tracking performance per model, and keeping everything read-only.

### Problems it solves

- Context overflow for local models with small context windows
- Invalid JSON responses breaking agent pipelines
- Tasks too large for modest local models (3B–14B params)
- Splitting large projects into manageable microtasks
- Per-model/per-profile benchmarks with confidence levels
- Integration with OpenCode, OpenClaw, and MCP agents
- Read-only audit of projects and folders
- Structured reports, logs, benchmarks, and model recommendations

### Key features

| Feature | Component | Description |
|---|---|---|
| Filesystem scanner | `governor/scanner.py` | Walk directories, detect profiles, compute hashes |
| Profile auto-detection | `governor/profile_detector.py` | Identify Python, JS/TS, PHP, Java, Docker, WordPress, etc. |
| Microtask generator | `governor/task_queue.py` | Convert scan results into prioritized pending tasks |
| Ollama provider | `governor/ollama_client.py` | Native `http://127.0.0.1:11434` chat provider |
| OpenAI-compatible provider | `governor/providers/` | Extensible provider architecture |
| JSON Guard | `governor/json_guard.py` | Parse, extract, validate, and repair model JSON output |
| SQLite memory | `governor/memory.py` | Reuse results by project path, file hash, model, prompt, and task type |
| Model profiles | `governor/model_profiles.py` | Track success rate, repair rate, and response time per model/task/profile |
| Prompt manager | `governor/prompt_manager.py` | Controlled prompt variants (v1, v2_strict_json, v3_short_schema) |
| Adaptive max chars | `governor/adaptive_limits.py` | Adjust file content limits from model statistics |
| Model benchmarks | `governor/model_benchmark.py` | Compare installed models on calibration fixtures |
| Profile benchmarks | `governor/profile_benchmark.py` | Compare models per project type |
| Model recommendations | `governor/model_recommendations.py` | Recommend model/prompt/limits with confidence levels |
| Patch suggester | `governor/patch_suggester.py` | Generate reviewable patch proposals without applying them |
| Audit report writer | `governor/report_writer.py` | Deterministic Markdown and JSON reports |
| Logs (JSONL) | Structured log subsystem | `localscope logs summary` for recent activity |
| Web UI | Local dashboard | `http://127.0.0.1:8765` — read-only report/log/benchmark viewer |
| MCP server | `adapters/mcp/server.py` | Expose high-level read-only tools to MCP clients |
| OpenCode adapter | `adapters/opencode/` | Wrapper CLI for OpenCode integration |
| OpenClaw adapter | `adapters/openclaw/` | Wrapper CLI for OpenClaw integration |
| Graphify optional context | `governor/prompt_renderer.py` | Consume Graphify output if present; never required |

### Architecture overview

```
                           adapters/
                    ┌────────────────────┐
                    │ OpenCode  OpenClaw  │
                    │    MCP     common   │
                    └────────┬───────────┘
                             │ AuditRequest / AuditResponse
                             ▼
                    ┌────────────────────┐
                    │    governor/main   │  ← CLI entry point
                    └────────┬───────────┘
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │   scanner    │  │  task_queue  │  │ task_runner  │
   │ + profile    │  │ + prioritize │  │ + ollama/    │
   │   detector   │  │              │  │   providers  │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                 │                 │
          ▼                 ▼                 ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ scan_result  │  │  tasks.json  │  │task_results  │
   │    .json     │  │              │  │    .json     │
   └──────────────┘  └──────────────┘  └──────┬───────┘
                                              │
          ┌───────────────────────────────────┤
          ▼                                   ▼
   ┌──────────────┐                    ┌──────────────┐
   │ report_writer│◄──── reducer ──────│   memory     │
   │   + reducer  │                    │  (SQLite)    │
   └──────┬───────┘                    └──────────────┘
          │
          ▼
   ┌────────────────────────────────────────────────┐
   │  reports/audit-YYYYMMDD-HHMMSS.md              │
   │  reports/audit-YYYYMMDD-HHMMSS.json            │
   │  reports/benchmarks/*.json                     │
   │  data/memory.sqlite                            │
   │  logs/*.jsonl                                  │
   └────────────────────────────────────────────────┘
```

Context providers:
- **Filesystem scanner** — always on, zero dependencies
- **Graphify** — optional, reads `graphify-out/graph.json` if present; never runs Graphify automatically

### Safety model

LocalScope is **read-only** toward analyzed targets. This is non-negotiable.

**LocalScope will never:**
- Modify analyzed files
- Execute shell commands on the analyzed project
- Apply patches automatically (`suggest-patch` only generates proposals)
- Expose `write_file`, `run_command`, `shell`, `exec`, or `apply_patch` through adapters
- Expose generic filesystem tools to agents
- Store secrets in logs or reports
- Download models automatically (Ollama models must be pulled manually)
- Perform fine-tuning (model profiles only track statistics)

**LocalScope only writes its own outputs:** `reports/`, `data/memory.sqlite`, and `logs/`.

`read_only=false` is rejected in all adapters. `max_tasks` is bounded to 1–100. Paths are validated — must exist, be directories, not filesystem roots.

### Supported targets

| Category | Examples |
|---|---|
| Languages | Python, JavaScript, TypeScript, Java, PHP |
| Platforms | WordPress, Docker |
| Configurations | Server config files, `.ini`, `.yaml`, `.json`, `.env` |
| Operating systems | Windows folders, Linux folders |
| General | Documentation, mixed folders, generic projects |

### Integrations

LocalScope integrates with AI agents through adapters and an MCP server — all outside the core package.

| Integration | Type | Entry point |
|---|---|---|
| **OpenCode** | Adapter + MCP | `adapters/opencode/local_scope_audit.py` |
| **OpenClaw** | Adapter | `adapters/openclaw/local_scope_audit.py` |
| **MCP** | Server (stdio) | `adapters/mcp/server.py` |
| **Graphify** | Optional context | Reads output; never required |

### Quick install

```powershell
git clone https://github.com/miacodeweb/localscope.git
cd localscope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
localscope --help
```

> If `localscope` is not found on PATH, use the compatible fallback:
> ```powershell
> python -m governor.main --help
> ```

### Quick start

```powershell
# Full audit (recommended one-shot)
localscope audit D:\path\to\project --profile auto --max-tasks 5

# Dry run — no model calls, validates pipeline only
localscope audit D:\path\to\project --profile auto --max-tasks 5 --dry-run

# Step-by-step for diagnostics
localscope scan D:\path\to\project
localscope tasks D:\path\to\project
localscope run-tasks D:\path\to\project --max-tasks 5
localscope report D:\path\to\project

# Use a specific model
localscope audit D:\path\to\project --profile auto --max-tasks 5 --model qwen3:8b

# Use benchmark-based recommendations
localscope audit D:\path\to\project --profile auto --max-tasks 5 --use-benchmark-recommendations
```

Compatible fallback form:

```powershell
python -m governor.main audit D:\path\to\project --profile auto --max-tasks 5
```

### Model benchmarking

Compare installed Ollama models to find the best one for each project type:

```powershell
# Benchmark models on a profile
localscope benchmark-profile python --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Calibrate across multiple profiles
localscope calibrate-models --profiles python javascript config_files --models qwen2.5-coder:7b qwen3:8b --max-tasks 5

# Show recommendations with confidence level
localscope model-recommendations --profile python
localscope model-recommendations --latest-benchmark --json
```

Confidence levels: `none` (0 samples) → `low` (1–4) → `medium` (5–14) → `high` (15+).

> No automatic model downloads. No fine-tuning. `config.yaml` is never modified.

### Web UI

```powershell
localscope webui
```

Opens a local read-only dashboard at `http://127.0.0.1:8765`. No external dependencies. Browse reports, logs, benchmarks, and model recommendations — never modifies projects.

### MCP / OpenCode / OpenClaw

**MCP server** exposes safe, high-level tools via stdio:

| Tool | Description |
|---|---|
| `localscope_audit` | Run a full read-only audit on a project path |
| `localscope_status` | Query recent audit status |
| `localscope_report` | Retrieve a compact summary for an existing report |
| `localscope_graph_info` | Inspect optional Graphify context |

No raw filesystem tools, no `write_file`, no `run_command`, no `shell`.

**OpenCode:**

```powershell
python -m adapters.opencode.local_scope_audit --path D:\path\to\project --profile auto --max-tasks 5 --read-only true
```

Outputs clean JSON to stdout for consumption as an external tool.

**OpenClaw:**

```powershell
python -m adapters.openclaw.local_scope_audit --path D:\path\to\project --profile auto --max-tasks 5 --read-only true
```

Returns JSON with report paths, counts, summary, and errors.

### Graphify (optional)

Graphify is an **optional external** context provider. LocalScope reads `graphify-out/graph.json` if present but never depends on it.

```powershell
# Optional: generate a Graphify knowledge graph externally
graphify D:\path\to\project

# Inspect Graphify output from within LocalScope
localscope graphify-info D:\path\to\project

# Run tasks — scanner fallback works fine without Graphify
localscope tasks D:\path\to\project
```

### Logs and troubleshooting

```powershell
# View recent log activity
localscope logs summary
```

Common issues:

| Problem | Solution |
|---|---|
| Ollama not responding | Run `ollama list`, `ollama serve`, then `localscope ollama-test` |
| Model not found | Run `ollama pull qwen2.5-coder:7b` or adjust `config.yaml` |
| Invalid JSON responses | Reduce `max_chars_per_file`, run fewer tasks, or use a stronger model |
| Graphify not detected | Check `graphify-out/graph.json` exists and run `graphify-info` |
| Windows paths with spaces | Quote paths: `"D:\My Project"` |
| `localscope` not found | Use fallback: `python -m governor.main --help` |

### Current status: v0.1.0-rc1

MVP release candidate. The `localscope` CLI is installable via `pip install -e .`. All core features are functional: scan, microtasks, Ollama/OpenAI-compatible providers, JSON Guard, SQLite memory, reports, benchmarks, model recommendations, MCP, Web UI, and adapters for OpenCode/OpenClaw.

### Roadmap

| Phase | Focus |
|---|---|
| **v0.1.0 (current)** | MVP: scan, tasks, Ollama, JSON Guard, memory, reports, benchmarks, MCP, Web UI |
| **Rebranding** | Migrate internal package from `governor/` → `localscope/` |
| **Performance** | Parallel task execution, report caching |
| **Providers** | Expand provider ecosystem beyond Ollama |
| **Quality** | Extended calibration fixtures, benchmark history |
| **Integrations** | First-class MCP support, richer agent adapters |

See [docs/ROADMAP.md](docs/ROADMAP.md) for details.

### Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Windows + WSL + Ollama](docs/WINDOWS_WSL_OLLAMA.md)
- [MCP Plan](docs/MCP_PLAN.md)
- [OpenCode Adapter](adapters/opencode/README.md)

---

## Español

### ¿Qué es LocalScope?

**LocalScope** ayuda a que los modelos locales trabajen de forma más confiable sobre proyectos reales, dividiendo carpetas y código en microtareas de solo lectura, validando respuestas, midiendo el rendimiento de cada modelo y generando reportes estructurados para agentes y desarrolladores.

Es una suite de análisis local y de solo lectura para proyectos y carpetas. Escanea proyectos, crea microtareas, utiliza modelos locales mediante Ollama o proveedores compatibles con OpenAI, valida cada respuesta con JSON Guard, almacena memoria reutilizable en SQLite, consume opcionalmente grafos de conocimiento Graphify y genera reportes determinísticos en Markdown/JSON.

> El nombre interno original del MVP fue **Claw Local Task Governor**. El producto y concepto actual es **LocalScope**. El paquete interno de Python aún se llama `governor/` por compatibilidad (futuro renombrado a `localscope/`).

### Por qué existe LocalScope

Los modelos locales suelen fallar cuando se usan con agentes sobre proyectos grandes porque reciben demasiado contexto, tareas poco definidas, outputs JSON inestables y poca visibilidad sobre errores. LocalScope divide el trabajo en microtareas, valida respuestas, guarda memoria, compara modelos, genera reportes y se integra con agentes como OpenCode y OpenClaw.

| Problema | Impacto |
|---|---|
| Demasiado contexto para el modelo | Entradas truncadas, salidas alucinadas, pérdida de detalles |
| Tareas demasiado grandes para modelos pequeños | Respuestas incompletas o inválidas |
| Salidas JSON inestables | Fallos en el parseo, agentes interrumpidos |
| Sin memoria entre ejecuciones | Trabajo redundante, resultados inconsistentes |
| Sin visibilidad de calidad del modelo | Difícil elegir el modelo adecuado |
| Sin modo seguro de solo lectura | Riesgo de modificar archivos sin querer |

**LocalScope resuelve cada uno de estos problemas.**

### Problemas que soluciona

- Desbordamiento de contexto en modelos locales con ventanas pequeñas
- Respuestas JSON inválidas que rompen pipelines de agentes
- Tareas excesivamente grandes para modelos modestos (3B–14B parámetros)
- División de proyectos grandes en microtareas manejables
- Benchmarks por modelo y perfil con niveles de confianza
- Integración con agentes OpenCode, OpenClaw y MCP
- Auditoría de solo lectura de proyectos y carpetas
- Reportes estructurados, logs, benchmarks y recomendaciones de modelos

### Funciones principales

| Función | Componente | Descripción |
|---|---|---|
| Escáner de archivos | `governor/scanner.py` | Recorre directorios, detecta perfiles, calcula hashes |
| Detección automática de perfil | `governor/profile_detector.py` | Identifica Python, JS/TS, PHP, Java, Docker, WordPress, etc. |
| Generador de microtareas | `governor/task_queue.py` | Convierte resultados del escaneo en tareas priorizadas |
| Proveedor Ollama | `governor/ollama_client.py` | Cliente nativo `http://127.0.0.1:11434` |
| Proveedor OpenAI-compatible | `governor/providers/` | Arquitectura extensible de proveedores |
| JSON Guard | `governor/json_guard.py` | Analiza, extrae, valida y repara JSON de modelos |
| Memoria SQLite | `governor/memory.py` | Reutiliza resultados por ruta, hash, modelo, prompt y tipo de tarea |
| Perfiles de modelo | `governor/model_profiles.py` | Registra tasa de éxito, tasa de reparación y tiempo de respuesta |
| Gestor de prompts | `governor/prompt_manager.py` | Variantes controladas (v1, v2_strict_json, v3_short_schema) |
| Límites adaptativos | `governor/adaptive_limits.py` | Ajusta max_chars según estadísticas del modelo |
| Benchmarks de modelos | `governor/model_benchmark.py` | Compara modelos instalados con fixtures de calibración |
| Benchmarks por perfil | `governor/profile_benchmark.py` | Compara modelos por tipo de proyecto |
| Recomendaciones | `governor/model_recommendations.py` | Recomienda modelo/prompt/límites con nivel de confianza |
| Sugerencia de parches | `governor/patch_suggester.py` | Genera propuestas de parches sin aplicarlos |
| Reportes de auditoría | `governor/report_writer.py` | Reportes determinísticos en Markdown y JSON |
| Logs (JSONL) | Subsistema de logs | `localscope logs summary` para actividad reciente |
| Web UI | Dashboard local | `http://127.0.0.1:8765` — visor de solo lectura |
| Servidor MCP | `adapters/mcp/server.py` | Herramientas de alto nivel para clientes MCP |
| Adaptador OpenCode | `adapters/opencode/` | CLI wrapper para OpenCode |
| Adaptador OpenClaw | `adapters/openclaw/` | CLI wrapper para OpenClaw |
| Graphify opcional | `governor/prompt_renderer.py` | Consume salida de Graphify si existe; nunca obligatorio |

### Arquitectura general

Misma arquitectura descrita en la sección en inglés: escáner → cola de tareas → ejecutor → reductor → reportes, con memoria SQLite y proveedores de contexto opcionales.

### Seguridad

LocalScope es **solo lectura** sobre los proyectos analizados. Esto no es negociable.

**LocalScope nunca:**
- Modifica archivos analizados
- Ejecuta comandos shell sobre el proyecto analizado
- Aplica parches automáticamente (`suggest-patch` solo genera sugerencias)
- Expone `write_file`, `run_command`, `shell`, `exec` o `apply_patch` mediante adaptadores
- Expone herramientas genéricas de sistema de archivos a agentes
- Guarda secretos en logs o reportes
- Descarga modelos automáticamente
- Realiza fine-tuning

Solo escribe sus propios archivos de salida: `reports/`, `data/memory.sqlite`, `logs/`.

### Objetivos soportados

Python, JavaScript, TypeScript, Java, PHP, WordPress, Docker, archivos de configuración, carpetas Windows/Linux, documentación y carpetas mixtas genéricas.

### Integraciones

| Integración | Tipo | Punto de entrada |
|---|---|---|
| **OpenCode** | Adaptador + MCP | `adapters/opencode/local_scope_audit.py` |
| **OpenClaw** | Adaptador | `adapters/openclaw/local_scope_audit.py` |
| **MCP** | Servidor (stdio) | `adapters/mcp/server.py` |
| **Graphify** | Contexto opcional | Lee salida; nunca obligatorio |

### Instalación rápida

```powershell
git clone https://github.com/miacodeweb/localscope.git
cd localscope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
localscope --help
```

> Si `localscope` no aparece en PATH, usar:
> ```powershell
> python -m governor.main --help
> ```

### Uso rápido

```powershell
# Auditoría completa (recomendado)
localscope audit D:\ruta\al\proyecto --profile auto --max-tasks 5

# Simulación — sin llamadas al modelo
localscope audit D:\ruta\al\proyecto --profile auto --max-tasks 5 --dry-run

# Paso a paso para diagnóstico
localscope scan D:\ruta\al\proyecto
localscope tasks D:\ruta\al\proyecto
localscope run-tasks D:\ruta\al\proyecto --max-tasks 5
localscope report D:\ruta\al\proyecto

# Usar un modelo específico
localscope audit D:\ruta\al\proyecto --profile auto --max-tasks 5 --model qwen3:8b

# Usar recomendaciones basadas en benchmarks
localscope audit D:\ruta\al\proyecto --profile auto --max-tasks 5 --use-benchmark-recommendations
```

### Benchmark de modelos

```powershell
localscope benchmark-profile python --models qwen2.5-coder:7b qwen3:8b --max-tasks 5
localscope calibrate-models --profiles python javascript config_files --models qwen2.5-coder:7b qwen3:8b --max-tasks 5
localscope model-recommendations --profile python
localscope model-recommendations --latest-benchmark --json
```

Niveles de confianza: `none` (0 muestras) → `low` (1–4) → `medium` (5–14) → `high` (15+).

### Web UI

```powershell
localscope webui
```

Abre un dashboard local de solo lectura en `http://127.0.0.1:8765`. Sin dependencias externas.

### MCP / OpenCode / OpenClaw

**MCP** expone herramientas seguras: `localscope_audit`, `localscope_status`, `localscope_report`, `localscope_graph_info`. Sin herramientas de sistema de archivos.

**OpenCode** y **OpenClaw** se integran mediante wrappers CLI que producen JSON limpio.

### Graphify (opcional)

Graphify es externo y opcional. LocalScope lee `graphify-out/graph.json` si existe; el escáner funciona sin él.

### Logs y solución de problemas

```powershell
localscope logs summary
```

| Problema | Solución |
|---|---|
| Ollama no responde | `ollama list`, `ollama serve`, luego `localscope ollama-test` |
| Modelo no encontrado | `ollama pull qwen2.5-coder:7b` |
| JSON inválido | Reduce `max_chars_per_file` o usa un modelo más potente |
| `localscope` no encontrado | Usar `python -m governor.main --help` |

### Estado actual: v0.1.0-rc1

Release candidate del MVP. CLI `localscope` instalable vía `pip install -e .`. Funcionalidades core completas: escaneo, microtareas, Ollama/proveedores OpenAI-compatibles, JSON Guard, memoria SQLite, reportes, benchmarks, recomendaciones, MCP, Web UI y adaptadores.

### Roadmap

| Fase | Foco |
|---|---|
| **v0.1.0 (actual)** | MVP completo |
| **Rebranding** | Migrar paquete interno de `governor/` → `localscope/` |
| **Rendimiento** | Ejecución paralela de tareas, caché de reportes |
| **Proveedores** | Expandir ecosistema más allá de Ollama |
| **Calidad** | Fixtures extendidos, historial de benchmarks |
| **Integraciones** | Soporte MCP de primera clase, adaptadores más ricos |

### Documentación

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Windows + WSL + Ollama](docs/WINDOWS_WSL_OLLAMA.md)

---

## Português

### O que é o LocalScope?

**LocalScope** ajuda modelos locais a trabalharem de forma mais confiável em projetos reais, dividindo pastas e código em microtarefas somente leitura, validando respostas, medindo o desempenho de cada modelo e gerando relatórios estruturados para agentes e desenvolvedores.

É uma suite de análise local e somente leitura para projetos e pastas. Escaneia projetos, cria microtarefas, utiliza modelos locais via Ollama ou provedores compatíveis com OpenAI, valida cada resposta com JSON Guard, armazena memória reutilizável em SQLite, consome opcionalmente grafos de conhecimento Graphify e gera relatórios determinísticos em Markdown/JSON.

> O nome interno original do MVP foi **Claw Local Task Governor**. O produto e conceito atual é **LocalScope**. O pacote interno Python ainda se chama `governor/` por compatibilidade (futura renomeação para `localscope/`).

### Por que o LocalScope existe

Modelos locais frequentemente falham quando usados com agentes em projetos grandes porque recebem contexto demais, tarefas mal definidas, saídas JSON instáveis e pouca visibilidade sobre erros. O LocalScope divide o trabalho em microtarefas, valida respostas, armazena memória, compara modelos, gera relatórios e se integra com agentes como OpenCode e OpenClaw.

| Problema | Impacto |
|---|---|
| Contexto excessivo para o modelo | Entradas truncadas, saídas alucinadas, perda de detalhes |
| Tarefas grandes demais para modelos pequenos | Respostas incompletas ou inválidas |
| Saídas JSON instáveis | Falhas de parsing, agentes interrompidos |
| Sem memória entre execuções | Trabalho redundante, resultados inconsistentes |
| Sem visibilidade de qualidade do modelo | Difícil escolher o modelo adequado |
| Sem modo seguro somente leitura | Risco de modificar arquivos sem querer |

**O LocalScope resolve cada um desses problemas.**

### Problemas que ele resolve

- Estouro de contexto em modelos locais com janelas pequenas
- Respostas JSON inválidas quebrando pipelines de agentes
- Tarefas muito grandes para modelos modestos (3B–14B parâmetros)
- Divisão de projetos grandes em microtarefas gerenciáveis
- Benchmarks por modelo e perfil com níveis de confiança
- Integração com agentes OpenCode, OpenClaw e MCP
- Auditoria somente leitura de projetos e pastas
- Relatórios estruturados, logs, benchmarks e recomendações de modelos

### Recursos principais

| Recurso | Componente | Descrição |
|---|---|---|
| Scanner de arquivos | `governor/scanner.py` | Percorre diretórios, detecta perfis, calcula hashes |
| Detecção automática de perfil | `governor/profile_detector.py` | Identifica Python, JS/TS, PHP, Java, Docker, WordPress, etc. |
| Gerador de microtarefas | `governor/task_queue.py` | Converte resultados do scanner em tarefas priorizadas |
| Provedor Ollama | `governor/ollama_client.py` | Cliente nativo `http://127.0.0.1:11434` |
| Provedor OpenAI-compatível | `governor/providers/` | Arquitetura extensível de provedores |
| JSON Guard | `governor/json_guard.py` | Analisa, extrai, valida e repara JSON de modelos |
| Memória SQLite | `governor/memory.py` | Reutiliza resultados por caminho, hash, modelo, prompt e tipo de tarefa |
| Perfis de modelo | `governor/model_profiles.py` | Registra taxa de sucesso, taxa de reparo e tempo de resposta |
| Gerenciador de prompts | `governor/prompt_manager.py` | Variantes controladas (v1, v2_strict_json, v3_short_schema) |
| Limites adaptativos | `governor/adaptive_limits.py` | Ajusta max_chars conforme estatísticas do modelo |
| Benchmarks de modelos | `governor/model_benchmark.py` | Compara modelos instalados com fixtures de calibração |
| Benchmarks por perfil | `governor/profile_benchmark.py` | Compara modelos por tipo de projeto |
| Recomendações | `governor/model_recommendations.py` | Recomenda modelo/prompt/limites com nível de confiança |
| Sugestão de patches | `governor/patch_suggester.py` | Gera propostas de patches sem aplicá-los |
| Relatórios de auditoria | `governor/report_writer.py` | Relatórios determinísticos em Markdown e JSON |
| Logs (JSONL) | Subsistema de logs | `localscope logs summary` para atividade recente |
| Web UI | Dashboard local | `http://127.0.0.1:8765` — visualizador somente leitura |
| Servidor MCP | `adapters/mcp/server.py` | Ferramentas de alto nível para clientes MCP |
| Adaptador OpenCode | `adapters/opencode/` | CLI wrapper para OpenCode |
| Adaptador OpenClaw | `adapters/openclaw/` | CLI wrapper para OpenClaw |
| Graphify opcional | `governor/prompt_renderer.py` | Consome saída do Graphify se presente; nunca obrigatório |

### Visão geral da arquitetura

Mesma arquitetura descrita na seção em inglês: scanner → fila de tarefas → executor → redutor → relatórios, com memória SQLite e provedores de contexto opcionais.

### Segurança

O LocalScope é **somente leitura** sobre os projetos analisados. Isto não é negociável.

**O LocalScope nunca:**
- Modifica arquivos analisados
- Executa comandos shell no projeto analisado
- Aplica patches automaticamente (`suggest-patch` apenas gera sugestões)
- Expõe `write_file`, `run_command`, `shell`, `exec` ou `apply_patch` através de adaptadores
- Expõe ferramentas genéricas de sistema de arquivos para agentes
- Armazena segredos em logs ou relatórios
- Baixa modelos automaticamente
- Realiza fine-tuning

Apenas grava seus próprios arquivos de saída: `reports/`, `data/memory.sqlite`, `logs/`.

### Alvos suportados

Python, JavaScript, TypeScript, Java, PHP, WordPress, Docker, arquivos de configuração, pastas Windows/Linux, documentação e pastas mistas genéricas.

### Integrações

| Integração | Tipo | Ponto de entrada |
|---|---|---|
| **OpenCode** | Adaptador + MCP | `adapters/opencode/local_scope_audit.py` |
| **OpenClaw** | Adaptador | `adapters/openclaw/local_scope_audit.py` |
| **MCP** | Servidor (stdio) | `adapters/mcp/server.py` |
| **Graphify** | Contexto opcional | Lê saída; nunca obrigatório |

### Instalação rápida

```powershell
git clone https://github.com/miacodeweb/localscope.git
cd localscope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
localscope --help
```

> Se `localscope` não for encontrado no PATH, use:
> ```powershell
> python -m governor.main --help
> ```

### Uso rápido

```powershell
# Auditoria completa (recomendado)
localscope audit D:\caminho\do\projeto --profile auto --max-tasks 5

# Simulação — sem chamadas ao modelo
localscope audit D:\caminho\do\projeto --profile auto --max-tasks 5 --dry-run

# Passo a passo para diagnóstico
localscope scan D:\caminho\do\projeto
localscope tasks D:\caminho\do\projeto
localscope run-tasks D:\caminho\do\projeto --max-tasks 5
localscope report D:\caminho\do\projeto

# Usar um modelo específico
localscope audit D:\caminho\do\projeto --profile auto --max-tasks 5 --model qwen3:8b

# Usar recomendações baseadas em benchmarks
localscope audit D:\caminho\do\projeto --profile auto --max-tasks 5 --use-benchmark-recommendations
```

### Benchmark de modelos

```powershell
localscope benchmark-profile python --models qwen2.5-coder:7b qwen3:8b --max-tasks 5
localscope calibrate-models --profiles python javascript config_files --models qwen2.5-coder:7b qwen3:8b --max-tasks 5
localscope model-recommendations --profile python
localscope model-recommendations --latest-benchmark --json
```

Níveis de confiança: `none` (0 amostras) → `low` (1–4) → `medium` (5–14) → `high` (15+).

### Web UI

```powershell
localscope webui
```

Abre um dashboard local somente leitura em `http://127.0.0.1:8765`. Sem dependências externas.

### MCP / OpenCode / OpenClaw

**MCP** expõe ferramentas seguras: `localscope_audit`, `localscope_status`, `localscope_report`, `localscope_graph_info`. Sem ferramentas de sistema de arquivos.

**OpenCode** e **OpenClaw** integram-se via wrappers CLI que produzem JSON limpo.

### Graphify (opcional)

Graphify é externo e opcional. O LocalScope lê `graphify-out/graph.json` se existir; o scanner funciona sem ele.

### Logs e solução de problemas

```powershell
localscope logs summary
```

| Problema | Solução |
|---|---|
| Ollama não responde | `ollama list`, `ollama serve`, depois `localscope ollama-test` |
| Modelo não encontrado | `ollama pull qwen2.5-coder:7b` |
| JSON inválido | Reduza `max_chars_per_file` ou use um modelo mais potente |
| `localscope` não encontrado | Use `python -m governor.main --help` |

### Estado atual: v0.1.0-rc1

Release candidate do MVP. CLI `localscope` instalável via `pip install -e .`. Funcionalidades core completas: escaneamento, microtarefas, Ollama/provedores OpenAI-compatíveis, JSON Guard, memória SQLite, relatórios, benchmarks, recomendações, MCP, Web UI e adaptadores.

### Roadmap

| Fase | Foco |
|---|---|
| **v0.1.0 (atual)** | MVP completo |
| **Rebranding** | Migrar pacote interno de `governor/` → `localscope/` |
| **Desempenho** | Execução paralela de tarefas, cache de relatórios |
| **Provedores** | Expandir ecossistema além do Ollama |
| **Qualidade** | Fixtures estendidos, histórico de benchmarks |
| **Integrações** | Suporte MCP de primeira classe, adaptadores mais ricos |

### Documentação

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Windows + WSL + Ollama](docs/WINDOWS_WSL_OLLAMA.md)

---

## Tests

```powershell
pytest
```
