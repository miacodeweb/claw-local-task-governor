"""Extensible project profile registry."""

from governor.profiles.registry import (
    DEFAULT_PROFILE,
    PROFILES_DIR,
    ProjectProfile,
    detect_profile_for_project,
    load_all_profiles,
    load_profile,
    match_profile,
    normalize_extension,
    profile_for_project,
    validate_profile_name,
)

__all__ = [
    "DEFAULT_PROFILE",
    "PROFILES_DIR",
    "ProjectProfile",
    "detect_profile_for_project",
    "load_all_profiles",
    "load_profile",
    "match_profile",
    "normalize_extension",
    "profile_for_project",
    "validate_profile_name",
]
