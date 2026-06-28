"""Compatibility alias for the OpenCode LocalScope audit adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.opencode.local_scope_audit import local_scope_audit


def local_project_audit(
    *,
    path: Path | str,
    profile: str = "auto",
    mode: str = "general",
    max_tasks: int = 5,
    use_memory: bool = True,
    use_graphify: bool = True,
    read_only: bool = True,
    output_dir: Path | str = "reports",
) -> dict[str, Any]:
    return local_scope_audit(
        path=path,
        profile=profile,
        mode=mode,
        max_tasks=max_tasks,
        use_memory=use_memory,
        use_graphify=use_graphify,
        read_only=read_only,
        output_dir=output_dir,
    )
