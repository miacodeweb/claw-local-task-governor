"""Controlled prompt variant selection for LocalScope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governor.model_profiles import DEFAULT_PROMPT_VERSION, ModelProfileStats, ModelProfileStore
from governor.prompt_renderer import PROMPTS_DIR, TASK_PROMPT_FILES, PromptRenderError, render_template


STRICT_JSON_VERSION = "v2_strict_json"
SHORT_SCHEMA_VERSION = "v3_short_schema"
MIN_HISTORY_RUNS = 3
HIGH_JSON_FAIL_RATE = 0.30
HIGH_MODEL_FAIL_RATE = 0.20
HIGH_TRUNCATION_RATE = 0.50


@dataclass(frozen=True)
class PromptVariant:
    task_type: str
    version: str
    path: str
    is_legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "version": self.version,
            "path": self.path,
            "is_legacy": self.is_legacy,
        }


@dataclass(frozen=True)
class PromptSelection:
    task_type: str
    version: str
    path: str
    reason: str
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "version": self.version,
            "path": self.path,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
        }


def list_prompt_variants(prompts_dir: Path | str = PROMPTS_DIR) -> list[PromptVariant]:
    root = Path(prompts_dir)
    variants: list[PromptVariant] = []
    for path in sorted(root.glob("*.txt")):
        parsed = _parse_versioned_prompt_name(path.name)
        if parsed is not None:
            task_type, version = parsed
            variants.append(PromptVariant(task_type=task_type, version=version, path=str(path)))
            continue

        task_type = _legacy_task_type_for_file(path.name)
        if task_type is not None and not (root / f"{task_type}.{DEFAULT_PROMPT_VERSION}.txt").exists():
            variants.append(
                PromptVariant(
                    task_type=task_type,
                    version=DEFAULT_PROMPT_VERSION,
                    path=str(path),
                    is_legacy=True,
                )
            )
    return variants


def resolve_prompt(
    task_type: str,
    prompt_version: str | None = None,
    *,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> PromptSelection:
    version = normalize_prompt_version(prompt_version)
    variants = {
        (variant.task_type, variant.version): variant
        for variant in list_prompt_variants(prompts_dir=prompts_dir)
    }
    selected = variants.get((task_type, version))
    if selected is not None:
        return PromptSelection(
            task_type=task_type,
            version=selected.version,
            path=selected.path,
            reason=f"resolved:{selected.version}",
        )

    fallback = variants.get((task_type, DEFAULT_PROMPT_VERSION))
    if fallback is None:
        template_name = TASK_PROMPT_FILES.get(task_type)
        if template_name is None:
            raise PromptRenderError(f"unsupported task type for prompt rendering: {task_type}")
        fallback_path = Path(prompts_dir) / template_name
        if not fallback_path.exists():
            raise PromptRenderError(f"prompt template not found for task type: {task_type}")
        fallback = PromptVariant(
            task_type=task_type,
            version=DEFAULT_PROMPT_VERSION,
            path=str(fallback_path),
            is_legacy=True,
        )

    return PromptSelection(
        task_type=task_type,
        version=fallback.version,
        path=fallback.path,
        reason=f"fallback:{version}_not_found",
        fallback_used=True,
    )


def select_prompt(
    *,
    model: str,
    task_type: str,
    profile: str,
    store: ModelProfileStore | None = None,
    manual_prompt_version: str | None = None,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> PromptSelection:
    if manual_prompt_version:
        selection = resolve_prompt(task_type, manual_prompt_version, prompts_dir=prompts_dir)
        if selection.fallback_used:
            return PromptSelection(
                task_type=selection.task_type,
                version=selection.version,
                path=selection.path,
                reason=f"manual_fallback:{manual_prompt_version}_not_found",
                fallback_used=True,
            )
        return PromptSelection(
            task_type=selection.task_type,
            version=selection.version,
            path=selection.path,
            reason="manual_prompt_version",
        )

    if store is None:
        selection = resolve_prompt(task_type, DEFAULT_PROMPT_VERSION, prompts_dir=prompts_dir)
        return PromptSelection(selection.task_type, selection.version, selection.path, "no_model_history")

    variants = list_prompt_variants(prompts_dir=prompts_dir)
    available_versions = {variant.version for variant in variants if variant.task_type == task_type}
    profiles = [
        item
        for item in store.list_profiles(model=model, task_type=task_type)
        if item.profile == profile and item.prompt_version in available_versions
    ]
    if not profiles:
        selection = resolve_prompt(task_type, DEFAULT_PROMPT_VERSION, prompts_dir=prompts_dir)
        return PromptSelection(selection.task_type, selection.version, selection.path, "no_model_history")

    best = _best_historical_profile(profiles)
    if best is not None:
        selection = resolve_prompt(task_type, best.prompt_version, prompts_dir=prompts_dir)
        return PromptSelection(
            selection.task_type,
            selection.version,
            selection.path,
            f"best_historical:{best.prompt_version}",
            selection.fallback_used,
        )

    latest = max(profiles, key=lambda item: (item.runs_count, item.updated_at))
    if latest.model_fail_rate > HIGH_MODEL_FAIL_RATE or latest.truncation_rate > HIGH_TRUNCATION_RATE:
        selection = resolve_prompt(task_type, SHORT_SCHEMA_VERSION, prompts_dir=prompts_dir)
        return PromptSelection(
            selection.task_type,
            selection.version,
            selection.path,
            "context_or_model_failures",
            selection.fallback_used,
        )

    if latest.json_fail_rate > HIGH_JSON_FAIL_RATE:
        selection = resolve_prompt(task_type, STRICT_JSON_VERSION, prompts_dir=prompts_dir)
        return PromptSelection(
            selection.task_type,
            selection.version,
            selection.path,
            "high_json_fail_rate",
            selection.fallback_used,
        )

    recommended = store.recommend_prompt_version(
        model=model,
        task_type=task_type,
        profile=profile,
        available_versions=available_versions,
    )
    selection = resolve_prompt(task_type, recommended, prompts_dir=prompts_dir)
    return PromptSelection(
        selection.task_type,
        selection.version,
        selection.path,
        f"recommended:{recommended}",
        selection.fallback_used,
    )


def render_managed_prompt(
    *,
    selection: PromptSelection,
    file_path: str,
    profile: str,
    task_type: str,
    file_content: str,
    task_id: str = "",
) -> str:
    template = Path(selection.path).read_text(encoding="utf-8")
    return render_template(
        template,
        {
            "task_id": task_id,
            "file_path": file_path,
            "profile": profile,
            "task_type": task_type,
            "file_content": file_content,
        },
    )


def recommend_prompt(
    *,
    model: str,
    task_type: str,
    profile: str = "general",
    store: ModelProfileStore | None = None,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> PromptSelection:
    return select_prompt(
        model=model,
        task_type=task_type,
        profile=profile,
        store=store,
        prompts_dir=prompts_dir,
    )


def normalize_prompt_version(prompt_version: str | None) -> str:
    version = str(prompt_version or DEFAULT_PROMPT_VERSION).strip()
    if version == "file-analysis-v1":
        return DEFAULT_PROMPT_VERSION
    return version or DEFAULT_PROMPT_VERSION


def _best_historical_profile(profiles: list[ModelProfileStats]) -> ModelProfileStats | None:
    mature = [item for item in profiles if item.runs_count >= MIN_HISTORY_RUNS]
    if not mature:
        return None
    best = max(
        mature,
        key=lambda item: (
            item.json_valid_rate,
            item.success_rate,
            -item.json_fail_rate,
            -item.model_fail_rate,
            item.runs_count,
        ),
    )
    if best.json_valid_rate >= 0.85 and best.success_rate >= 0.80:
        return best
    return None


def _parse_versioned_prompt_name(filename: str) -> tuple[str, str] | None:
    match = re.match(r"^(?P<task>inspect_[a-z_]+_file)\.(?P<version>v[0-9][a-z0-9_]*)\.txt$", filename)
    if match is None:
        return None
    return match.group("task"), match.group("version")


def _legacy_task_type_for_file(filename: str) -> str | None:
    for task_type, template_name in TASK_PROMPT_FILES.items():
        if filename == template_name:
            return task_type
    return None
