"""Common audit request contract used by LocalScope adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from governor.safety import normalize_path_text, validate_max_tasks


ALLOWED_PROFILES = {
    "auto",
    "general",
    "php",
    "wordpress",
    "javascript",
    "python",
    "java",
    "docker",
    "config_files",
    "windows_folder",
    "linux_folder",
    "documentation",
}
ALLOWED_MODES = {"general", "security", "code_quality", "config_audit"}
CORE_PROFILE_ALIASES = {
    "windows_folder": "general",
    "linux_folder": "general",
    "documentation": "general",
}


@dataclass(frozen=True)
class AuditRequest:
    path: str
    profile: str = "auto"
    mode: str = "general"
    max_tasks: int = 5
    use_memory: bool = True
    use_graphify: bool = True
    use_adaptive_limits: bool = True
    prompt_version: str | None = None
    read_only: bool = True
    model_override: str | None = None
    use_benchmark_recommendations: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditRequest":
        request = cls(
            path=normalize_path_text(data.get("path", "")),
            profile=normalize_choice(data.get("profile", "auto")),
            mode=normalize_choice(data.get("mode", "general")),
            max_tasks=validate_max_tasks(data.get("max_tasks", 5)),
            use_memory=parse_bool(data.get("use_memory", True)),
            use_graphify=parse_bool(data.get("use_graphify", True)),
            use_adaptive_limits=parse_bool(data.get("use_adaptive_limits", True)),
            prompt_version=normalize_optional_text(data.get("prompt_version")),
            read_only=parse_bool(data.get("read_only", True)),
            model_override=normalize_optional_text(data.get("model_override", data.get("model"))),
            use_benchmark_recommendations=parse_bool(data.get("use_benchmark_recommendations", False)),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not self.path:
            raise ValueError("path is required")
        if self.profile not in ALLOWED_PROFILES:
            raise ValueError(f"profile must be one of: {', '.join(sorted(ALLOWED_PROFILES))}")
        if self.mode not in ALLOWED_MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(ALLOWED_MODES))}")

    @property
    def core_profile(self) -> str:
        return CORE_PROFILE_ALIASES.get(self.profile, self.profile)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_choice(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
