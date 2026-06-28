"""Project profile detection for the Phase 1 scanner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from governor.profiles import detect_profile_for_project, profile_for_project


@dataclass(frozen=True)
class ProfileSignal:
    profile: str
    confidence: float
    reason: str


def detect_profiles(root: Path, forced_profile: str | None = None) -> list[ProfileSignal]:
    """Return ranked project profile signals for a workspace root."""
    root = root.resolve()
    if forced_profile and forced_profile != "auto":
        _profile, matches = detect_profile_for_project(root, forced_profile=forced_profile)
        return [
            ProfileSignal(profile=profile.name, confidence=confidence, reason=reason)
            for profile, confidence, reason in matches
        ]
    return [
        ProfileSignal(profile=profile.name, confidence=confidence, reason=reason)
        for profile, confidence, reason in profile_for_project(root)
    ]


def detect_best_profile(root: Path, forced_profile: str | None = None) -> ProfileSignal:
    """Return the highest-confidence project profile."""
    return detect_profiles(root, forced_profile=forced_profile)[0]
