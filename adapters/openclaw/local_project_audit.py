"""Compatibility alias for the OpenClaw LocalScope audit adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governor.memory import SQLiteMemory
from governor.ollama_client import OllamaClient

from adapters.openclaw.local_scope_audit import local_scope_audit


def local_project_audit(
    *,
    path: Path | str,
    profile: str = "auto",
    mode: str = "general",
    max_tasks: int | None = None,
    max_files: int | None = None,
    use_memory: bool = True,
    use_graphify: bool = True,
    read_only: bool = True,
    output_dir: Path | str = "reports",
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> dict[str, Any]:
    return local_scope_audit(
        path=path,
        profile=profile,
        mode=mode,
        max_tasks=max_tasks,
        max_files=max_files,
        use_memory=use_memory,
        use_graphify=use_graphify,
        read_only=read_only,
        output_dir=output_dir,
        client=client,
        memory=memory,
    )
