"""Generic read-only scanner for Phase 1."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from governor.profile_detector import ProfileSignal, detect_profiles
from governor.profiles import ProjectProfile, load_profile, validate_profile_name


IGNORE_DIR_NAMES = {
    ".cache",
    ".git",
    ".idea",
    ".tmp",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "cache",
    "coverage",
    "dist",
    "logs",
    "node_modules",
    "tmp",
    "vendor",
    "venv",
}

IGNORE_DIR_PARTS = {
    ("wp-content", "uploads"),
    ("wp-content", "cache"),
}

IGNORE_FILE_SUFFIXES = {
    ".7z",
    ".avi",
    ".bin",
    ".dll",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".map",
    ".mov",
    ".mp4",
    ".pdf",
    ".png",
    ".rar",
    ".so",
    ".svg",
    ".tar",
    ".webp",
    ".zip",
}

IGNORE_FILE_ENDINGS = {
    ".min.css",
    ".min.js",
    ".tar.gz",
}

RELEVANT_EXTENSIONS = {
    ".cs",
    ".css",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}

RELEVANT_FILENAMES = {
    ".env.example",
    "Dockerfile",
    "build.gradle",
    "composer.json",
    "docker-compose.yml",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
}

SECRET_LIKE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
}

HIGH_IMPORTANCE_FILENAMES = {
    "Dockerfile",
    "build.gradle",
    "composer.json",
    "docker-compose.yml",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "wp-config.php",
}


@dataclass(frozen=True)
class ScannedFile:
    path: str
    size: int
    extension: str
    modified_at: str
    sha256: str | None
    relevant: bool
    importance: str
    secret_like: bool


@dataclass(frozen=True)
class IgnoredPath:
    path: str
    reason: str


@dataclass(frozen=True)
class ScanResult:
    root: str
    generated_at: str
    profile_detected: str
    profiles: list[ProfileSignal]
    files_found: int
    files_ignored: int
    relevant_files: int
    files: list[ScannedFile]
    ignored: list[IgnoredPath]

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "generated_at": self.generated_at,
            "profile_detected": self.profile_detected,
            "profiles": [asdict(profile) for profile in self.profiles],
            "files_found": self.files_found,
            "files_ignored": self.files_ignored,
            "relevant_files": self.relevant_files,
            "files": [asdict(file) for file in self.files],
            "ignored": [asdict(item) for item in self.ignored],
        }


def scan_project(
    target_path: Path | str,
    output_dir: Path | str = "reports",
    profile: str | None = "auto",
) -> ScanResult:
    """Scan a project folder without modifying files inside it."""
    root = _resolve_existing_directory(Path(target_path))
    profile_name = validate_profile_name(profile or "auto")
    output_paths = {
        (Path(output_dir) / "scan_result.json").resolve(),
        (Path(output_dir) / "tasks.json").resolve(),
        (Path(output_dir) / "task_results.json").resolve(),
    }
    profiles = detect_profiles(root, forced_profile=profile_name)
    profile_rules = load_profile(profiles[0].profile)
    ignored: list[IgnoredPath] = []
    files: list[ScannedFile] = []
    files_found = 0

    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        _filter_ignored_dirs(root, current_path, dir_names, ignored, profile_rules.ignore_dirs)

        for file_name in sorted(file_names):
            file_path = current_path / file_name
            relative_path = _relative_posix(root, file_path)

            if file_path.resolve(strict=False) in output_paths:
                ignored.append(IgnoredPath(path=relative_path, reason="governor output file"))
                continue

            if _is_symlink_outside_root(root, file_path):
                ignored.append(IgnoredPath(path=relative_path, reason="symlink outside root"))
                continue

            if file_path.is_symlink():
                ignored.append(IgnoredPath(path=relative_path, reason="symlink skipped"))
                continue

            if should_ignore_file(file_path):
                ignored.append(IgnoredPath(path=relative_path, reason="ignored file type"))
                continue

            try:
                stat = file_path.stat()
            except OSError:
                ignored.append(IgnoredPath(path=relative_path, reason="could not stat file"))
                continue

            if not file_path.is_file():
                continue

            files_found += 1
            relevant = is_relevant_file(file_path, profile_rules)
            sha256 = sha256_file(file_path) if relevant else None
            files.append(
                ScannedFile(
                    path=relative_path,
                    size=stat.st_size,
                    extension=file_path.suffix.lower(),
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    sha256=sha256,
                    relevant=relevant,
                    importance=rank_importance(file_path, relevant, profile_rules),
                    secret_like=is_secret_like(file_path),
                )
            )

    files = sorted(files, key=_file_sort_key)
    result = ScanResult(
        root=str(root),
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile_detected=profiles[0].profile,
        profiles=profiles,
        files_found=files_found,
        files_ignored=len(ignored),
        relevant_files=sum(1 for item in files if item.relevant),
        files=files,
        ignored=sorted(ignored, key=lambda item: item.path),
    )

    write_scan_result(result, output_dir)
    return result


def write_scan_result(result: ScanResult, output_dir: Path | str = "reports") -> Path:
    """Write reports/scan_result.json for a completed scan."""
    output_path = Path(output_dir) / "scan_result.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return output_path


def should_ignore_file(path: Path) -> bool:
    lower_name = path.name.lower()
    return lower_name.endswith(tuple(IGNORE_FILE_ENDINGS)) or path.suffix.lower() in IGNORE_FILE_SUFFIXES


def is_relevant_file(path: Path, profile: ProjectProfile | None = None) -> bool:
    profile_extensions = profile.relevant_extensions if profile else set()
    profile_files = profile.important_files if profile else set()
    return (
        path.name in RELEVANT_FILENAMES
        or path.name in profile_files
        or path.name in SECRET_LIKE_FILENAMES
        or path.suffix.lower() in RELEVANT_EXTENSIONS
        or path.suffix.lower() in profile_extensions
    )


def is_secret_like(path: Path) -> bool:
    lower_name = path.name.lower()
    return lower_name in SECRET_LIKE_FILENAMES or "secret" in lower_name or "credential" in lower_name


def rank_importance(path: Path, relevant: bool, profile: ProjectProfile | None = None) -> str:
    if not relevant:
        return "ignored"
    profile_files = profile.important_files if profile else set()
    if path.name in HIGH_IMPORTANCE_FILENAMES or path.name in profile_files or path.name in SECRET_LIKE_FILENAMES:
        return "high"
    if path.suffix.lower() in {".py", ".js", ".ts", ".php", ".java", ".go", ".rs"}:
        return "medium"
    return "low"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_existing_directory(path: Path) -> Path:
    root = path.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"scan target is not a directory: {root}")
    return root


def _filter_ignored_dirs(
    root: Path,
    current_path: Path,
    dir_names: list[str],
    ignored: list[IgnoredPath],
    profile_ignore_dirs: set[str] | None = None,
) -> None:
    kept: list[str] = []
    profile_ignore_dirs = profile_ignore_dirs or set()
    for dir_name in sorted(dir_names):
        child = current_path / dir_name
        relative = _relative_posix(root, child)

        if child.is_symlink():
            ignored.append(IgnoredPath(path=relative, reason="symlink directory skipped"))
            continue

        if (
            dir_name.lower() in IGNORE_DIR_NAMES
            or relative.lower() in profile_ignore_dirs
            or dir_name.lower() in profile_ignore_dirs
            or _matches_ignored_dir_parts(root, child)
        ):
            ignored.append(IgnoredPath(path=relative, reason="ignored directory"))
            continue

        kept.append(dir_name)

    dir_names[:] = kept


def _matches_ignored_dir_parts(root: Path, path: Path) -> bool:
    parts = tuple(part.lower() for part in path.relative_to(root).parts)
    for ignored_parts in IGNORE_DIR_PARTS:
        if len(parts) >= len(ignored_parts) and parts[-len(ignored_parts) :] == ignored_parts:
            return True
    return False


def _is_symlink_outside_root(root: Path, path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return True
    return not _is_relative_to(resolved, root)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _file_sort_key(file: ScannedFile) -> tuple[int, str]:
    importance_order = {"high": 0, "medium": 1, "low": 2, "ignored": 3}
    return (importance_order.get(file.importance, 4), file.path)
