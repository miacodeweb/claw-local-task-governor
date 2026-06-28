"""Registry for generic and language-specific project profiles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"
DEFAULT_PROFILE = "general"
ALLOWED_BASE_PRIORITIES = {"low", "medium", "high"}


@dataclass(frozen=True)
class ProjectProfile:
    name: str
    relevant_extensions: set[str] = field(default_factory=set)
    important_files: set[str] = field(default_factory=set)
    ignore_dirs: set[str] = field(default_factory=set)
    risk_patterns: list[str] = field(default_factory=list)
    recommended_prompt: str = "inspect_code_file.txt"
    base_priority: str = "low"
    markers: dict[str, Any] = field(default_factory=dict)


BUILTIN_PROFILES: dict[str, ProjectProfile] = {
    "general": ProjectProfile(
        name="general",
        relevant_extensions={".md", ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css"},
        important_files={"README.md", "CHANGELOG.md", "Dockerfile", "docker-compose.yml"},
        risk_patterns=["password", "secret", "token", "api_key"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="low",
        markers={"confidence": 0.4},
    ),
    "php": ProjectProfile(
        name="php",
        relevant_extensions={".php", ".phtml", ".inc"},
        important_files={"composer.json", "composer.lock", ".htaccess"},
        ignore_dirs={"vendor"},
        risk_patterns=["eval(", "shell_exec", "unserialize", "$_GET", "$_POST"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="medium",
        markers={"files": ["composer.json"], "confidence": 0.75},
    ),
    "wordpress": ProjectProfile(
        name="wordpress",
        relevant_extensions={".php", ".js", ".css", ".json"},
        important_files={"wp-config.php", "functions.php", "style.css", "composer.json"},
        ignore_dirs={"wp-content/uploads", "wp-content/cache"},
        risk_patterns=["ABSPATH", "wp_nonce", "current_user_can", "$wpdb", "sanitize_"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="medium",
        markers={"all_files": ["wp-config.php"], "all_dirs": ["wp-content"], "confidence": 0.95},
    ),
    "javascript": ProjectProfile(
        name="javascript",
        relevant_extensions={".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
        important_files={"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json"},
        ignore_dirs={"node_modules", "dist", "build", "coverage"},
        risk_patterns=["eval(", "innerHTML", "process.env", "child_process", "dangerouslySetInnerHTML"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="medium",
        markers={"files": ["package.json"], "confidence": 0.75},
    ),
    "python": ProjectProfile(
        name="python",
        relevant_extensions={".py", ".pyi"},
        important_files={"pyproject.toml", "requirements.txt", "setup.py", "poetry.lock"},
        ignore_dirs={"__pycache__", ".venv", "venv"},
        risk_patterns=["eval(", "exec(", "pickle.loads", "subprocess", "os.system"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="medium",
        markers={"files": ["pyproject.toml", "requirements.txt"], "confidence": 0.75},
    ),
    "java": ProjectProfile(
        name="java",
        relevant_extensions={".java", ".gradle", ".xml"},
        important_files={"pom.xml", "build.gradle", "settings.gradle", "gradle.properties"},
        ignore_dirs={"target", "build", ".gradle"},
        risk_patterns=["Runtime.getRuntime", "ProcessBuilder", "ObjectInputStream", "System.getenv"],
        recommended_prompt="inspect_code_file.txt",
        base_priority="medium",
        markers={"files": ["pom.xml", "build.gradle"], "confidence": 0.75},
    ),
    "docker": ProjectProfile(
        name="docker",
        relevant_extensions={".yml", ".yaml", ".env"},
        important_files={"Dockerfile", "docker-compose.yml", "compose.yaml", ".dockerignore"},
        risk_patterns=["latest", "privileged", "hostNetwork", "password", "secret"],
        recommended_prompt="inspect_config_file.txt",
        base_priority="medium",
        markers={"files": ["Dockerfile", "docker-compose.yml", "compose.yaml"], "confidence": 0.7},
    ),
    "config_files": ProjectProfile(
        name="config_files",
        relevant_extensions={".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".env", ".example"},
        important_files={"settings.json", "app.yaml", "app.toml", ".env.example", "config.yaml"},
        risk_patterns=["password", "secret", "token", "api_key", "private_key"],
        recommended_prompt="inspect_config_file.txt",
        base_priority="medium",
        markers={"files": ["settings.json", "app.yaml", "app.toml", ".env.example"], "confidence": 0.65},
    ),
    "windows_folder": ProjectProfile(
        name="windows_folder",
        relevant_extensions={".ps1", ".bat", ".cmd", ".ini", ".json", ".yaml", ".yml", ".md", ".txt"},
        important_files={"README.md", "desktop.ini", "settings.json"},
        ignore_dirs={"$recycle.bin", "system volume information"},
        risk_patterns=["password", "secret", "token", "credential"],
        recommended_prompt="inspect_config_file.txt",
        base_priority="low",
        markers={"confidence": 0.35, "fallback": "general"},
    ),
    "linux_folder": ProjectProfile(
        name="linux_folder",
        relevant_extensions={".sh", ".conf", ".service", ".timer", ".json", ".yaml", ".yml", ".md", ".txt"},
        important_files={"README.md", ".env.example", "nginx.conf", "systemd.service"},
        ignore_dirs={".cache"},
        risk_patterns=["password", "secret", "token", "sudo", "chmod 777"],
        recommended_prompt="inspect_config_file.txt",
        base_priority="low",
        markers={"confidence": 0.35, "fallback": "general"},
    ),
    "documentation": ProjectProfile(
        name="documentation",
        relevant_extensions={".md", ".rst", ".txt", ".adoc"},
        important_files={"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "docs"},
        risk_patterns=["password", "secret", "token"],
        recommended_prompt="inspect_documentation_file.txt",
        base_priority="low",
        markers={"dirs": ["docs"], "confidence": 0.5},
    ),
}


def load_profile(name: str, profiles_dir: Path | str = PROFILES_DIR) -> ProjectProfile:
    """Load one profile by name; fall back to general if it is missing."""
    normalized = normalize_profile_name(name)
    base = BUILTIN_PROFILES.get(normalized)
    if base is None:
        if normalized != DEFAULT_PROFILE:
            return load_profile(DEFAULT_PROFILE, profiles_dir)
        base = BUILTIN_PROFILES[DEFAULT_PROFILE]

    rules_path = Path(profiles_dir) / normalized / "rules.yaml"
    if not rules_path.is_file():
        return base

    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base

    return profile_from_mapping(data, fallback=base)


def load_all_profiles(profiles_dir: Path | str = PROFILES_DIR) -> dict[str, ProjectProfile]:
    """Load built-in profiles, optionally overlaid by local rules files."""
    profiles = dict(BUILTIN_PROFILES)
    root = Path(profiles_dir)
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "rules.yaml").is_file():
                profile = load_profile(child.name, profiles_dir)
                profiles[profile.name] = profile
    profiles.setdefault(DEFAULT_PROFILE, BUILTIN_PROFILES[DEFAULT_PROFILE])
    return profiles


def profile_for_project(root: Path, profiles_dir: Path | str = PROFILES_DIR) -> list[tuple[ProjectProfile, float, str]]:
    """Return matching profiles with confidence and reason."""
    matches = []
    for profile in load_all_profiles(profiles_dir).values():
        if profile.name == DEFAULT_PROFILE:
            continue
        confidence, reason = match_profile(root, profile)
        if confidence > 0:
            matches.append((profile, confidence, reason))

    if not matches:
        general = load_profile(DEFAULT_PROFILE, profiles_dir)
        matches.append((general, 0.4, "no known project markers found"))

    return sorted(matches, key=lambda item: item[1], reverse=True)


def detect_profile_for_project(
    root: Path,
    *,
    forced_profile: str | None = None,
    profiles_dir: Path | str = PROFILES_DIR,
) -> tuple[ProjectProfile, list[tuple[ProjectProfile, float, str]]]:
    """Return the selected profile and all detected profile signals."""
    if forced_profile and forced_profile != "auto":
        profile = load_profile(validate_profile_name(forced_profile, profiles_dir), profiles_dir)
        return profile, [(profile, 1.0, "profile forced by user")]

    matches = profile_for_project(root, profiles_dir)
    return matches[0][0], matches


def match_profile(root: Path, profile: ProjectProfile) -> tuple[float, str]:
    markers = profile.markers
    marker_files = [str(item) for item in markers.get("files", [])]
    marker_dirs = [str(item) for item in markers.get("dirs", [])]
    all_files = [str(item) for item in markers.get("all_files", [])]
    all_dirs = [str(item) for item in markers.get("all_dirs", [])]

    if all_files and not all((root / item).is_file() for item in all_files):
        return 0.0, ""
    if all_dirs and not all((root / item).is_dir() for item in all_dirs):
        return 0.0, ""
    if all_files or all_dirs:
        pieces = all_files + all_dirs
        return float(markers.get("confidence", 0.8)), f"{', '.join(pieces)} found"

    found_files = [item for item in marker_files if (root / item).is_file()]
    found_dirs = [item for item in marker_dirs if (root / item).is_dir()]
    found = found_files + found_dirs
    if found:
        return float(markers.get("confidence", 0.7)), f"{', '.join(found)} found"

    return 0.0, ""


def validate_profile_name(name: str, profiles_dir: Path | str = PROFILES_DIR) -> str:
    normalized = normalize_profile_name(name)
    if normalized == "auto":
        return normalized
    if normalized not in load_all_profiles(profiles_dir):
        allowed = ", ".join(["auto", *sorted(load_all_profiles(profiles_dir))])
        raise ValueError(f"profile must be one of: {allowed}")
    return normalized


def profile_from_mapping(data: dict[str, Any], *, fallback: ProjectProfile) -> ProjectProfile:
    name = str(data.get("name") or fallback.name)
    base_priority = str(data.get("base_priority") or fallback.base_priority).lower()
    if base_priority not in ALLOWED_BASE_PRIORITIES:
        base_priority = fallback.base_priority

    return replace(
        fallback,
        name=name,
        relevant_extensions={normalize_extension(item) for item in data.get("relevant_extensions", fallback.relevant_extensions)},
        important_files={str(item) for item in data.get("important_files", fallback.important_files)},
        ignore_dirs={str(item).lower() for item in data.get("ignore_dirs", fallback.ignore_dirs)},
        risk_patterns=[str(item) for item in data.get("risk_patterns", fallback.risk_patterns)],
        recommended_prompt=str(data.get("recommended_prompt") or fallback.recommended_prompt),
        base_priority=base_priority,
        markers=dict(data.get("markers", fallback.markers)),
    )


def normalize_extension(extension: str) -> str:
    extension = str(extension).strip()
    if not extension:
        return extension
    return extension if extension.startswith(".") else f".{extension}"


def normalize_profile_name(name: str | None) -> str:
    return str(name or DEFAULT_PROFILE).strip().lower()
