"""Extensible project profile rules."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
DEFAULT_PROFILE = "general"


@dataclass(frozen=True)
class ProjectProfile:
    name: str
    relevant_extensions: set[str] = field(default_factory=set)
    important_files: set[str] = field(default_factory=set)
    ignore_dirs: set[str] = field(default_factory=set)
    risk_patterns: list[str] = field(default_factory=list)
    recommended_prompt: str = "inspect_code_file.txt"
    markers: dict[str, Any] = field(default_factory=dict)


def load_profile(name: str, profiles_dir: Path | str = PROFILES_DIR) -> ProjectProfile:
    """Load one profile; fall back to general if it is missing."""
    profile_dir = Path(profiles_dir) / name
    rules_path = profile_dir / "rules.yaml"
    if not rules_path.is_file() and name != DEFAULT_PROFILE:
        return load_profile(DEFAULT_PROFILE, profiles_dir)
    if not rules_path.is_file():
        return ProjectProfile(name=DEFAULT_PROFILE)

    data = json.loads(rules_path.read_text(encoding="utf-8"))
    return ProjectProfile(
        name=str(data.get("name") or name),
        relevant_extensions={normalize_extension(item) for item in data.get("relevant_extensions", [])},
        important_files={str(item) for item in data.get("important_files", [])},
        ignore_dirs={str(item).lower() for item in data.get("ignore_dirs", [])},
        risk_patterns=[str(item) for item in data.get("risk_patterns", [])],
        recommended_prompt=str(data.get("recommended_prompt") or "inspect_code_file.txt"),
        markers=dict(data.get("markers", {})),
    )


def load_all_profiles(profiles_dir: Path | str = PROFILES_DIR) -> dict[str, ProjectProfile]:
    """Load all profile directories that contain rules.yaml."""
    root = Path(profiles_dir)
    profiles: dict[str, ProjectProfile] = {}
    if not root.is_dir():
        profiles[DEFAULT_PROFILE] = ProjectProfile(name=DEFAULT_PROFILE)
        return profiles

    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "rules.yaml").is_file():
            profile = load_profile(child.name, profiles_dir)
            profiles[profile.name] = profile

    profiles.setdefault(DEFAULT_PROFILE, ProjectProfile(name=DEFAULT_PROFILE))
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


def normalize_extension(extension: str) -> str:
    extension = str(extension).strip()
    if not extension:
        return extension
    return extension if extension.startswith(".") else f".{extension}"
