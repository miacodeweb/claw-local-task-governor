"""Common audit response contract used by LocalScope adapters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


ALLOWED_STATUSES = {"completed", "failed"}
ALLOWED_ADAPTERS = {"openclaw", "opencode", "cli", "mcp"}


@dataclass(frozen=True)
class AuditResponse:
    status: str
    adapter: str
    project_path: str = ""
    profile_detected: str = ""
    report_markdown: str = ""
    report_json: str = ""
    tasks_processed: int = 0
    reused: int = 0
    json_valid: int = 0
    json_repaired: int = 0
    json_failed: int = 0
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    model_used: str = ""
    benchmark_source: str = ""
    prompt_version_used: str = ""
    max_chars_used: int = 0
    adaptive_limits_enabled: bool = False

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")
        if self.adapter not in ALLOWED_ADAPTERS:
            raise ValueError(f"adapter must be one of: {', '.join(sorted(ALLOWED_ADAPTERS))}")
        object.__setattr__(self, "errors", [str(error) for error in self.errors])

    @classmethod
    def failed(
        cls,
        *,
        adapter: str,
        project_path: str = "",
        summary: str,
        errors: list[str] | None = None,
    ) -> "AuditResponse":
        return cls(
            status="failed",
            adapter=adapter,
            project_path=str(project_path),
            summary=summary,
            errors=errors or [summary],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
