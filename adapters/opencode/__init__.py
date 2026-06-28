"""OpenCode adapter surface for LocalScope."""

from __future__ import annotations

from typing import Any


__all__ = ["local_project_audit", "local_scope_audit"]


def __getattr__(name: str) -> Any:
    if name == "local_scope_audit":
        from adapters.opencode.local_scope_audit import local_scope_audit

        return local_scope_audit
    if name == "local_project_audit":
        from adapters.opencode.local_project_audit import local_project_audit

        return local_project_audit
    raise AttributeError(name)
