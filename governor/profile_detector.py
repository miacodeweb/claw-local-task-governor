"""Project profile detection for the Phase 1 scanner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from governor.profiles import profile_for_project


@dataclass(frozen=True)
class ProfileSignal:
    profile: str
    confidence: float
    reason: str


def detect_profiles(root: Path) -> list[ProfileSignal]:
    """Return ranked project profile signals for a workspace root."""
    root = root.resolve()
    return [
        ProfileSignal(profile=profile.name, confidence=confidence, reason=reason)
        for profile, confidence, reason in profile_for_project(root)
    ]


def detect_best_profile(root: Path) -> ProfileSignal:
    """Return the highest-confidence project profile."""
    return detect_profiles(root)[0]
