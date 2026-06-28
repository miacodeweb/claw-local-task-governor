"""Generate reviewable patch suggestions without applying them."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from governor.json_guard import guard_json
from governor.ollama_client import OllamaClient, OllamaError, load_ollama_config


PATCH_WARNING = "Not applied automatically"
PATCHES_DIRNAME = "patches"
PROMPT_PATH = Path("prompts") / "suggest_patch.txt"
PATCH_SCHEMA_PATH = Path("patch_suggestion.schema.json")
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class PatchSuggestion:
    status: str
    file_path: str
    finding_type: str
    severity: str
    summary: str
    diff: str
    not_applied: bool
    errors: list[str]
    patch_markdown: str = ""
    patch_json: str = ""
    model: str = ""
    finding: dict[str, Any] | None = None

    def to_schema_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "file_path": self.file_path,
            "finding_type": self.finding_type,
            "severity": self.severity,
            "summary": self.summary,
            "diff": self.diff,
            "not_applied": self.not_applied,
            "errors": list(self.errors),
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.to_schema_dict()
        data.update(
            {
                "patch_markdown": self.patch_markdown,
                "patch_json": self.patch_json,
                "model": self.model,
                "finding": self.finding or {},
                "warning": PATCH_WARNING,
            }
        )
        return data


@dataclass(frozen=True)
class PatchSuggestionSummary:
    mode: str
    status: str
    project_path: str
    report_path: str
    output_dir: str
    warning: str
    dry_run: bool
    findings_considered: int
    patches_created: int
    patches_failed: int
    candidates: list[dict[str, Any]]
    suggestions: list[PatchSuggestion]

    @property
    def proposals(self) -> list[PatchSuggestion]:
        """Compatibility alias for older callers."""
        return self.suggestions

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "project_path": self.project_path,
            "report_path": self.report_path,
            "output_dir": self.output_dir,
            "warning": self.warning,
            "dry_run": self.dry_run,
            "findings_considered": self.findings_considered,
            "patches_created": self.patches_created,
            "patches_failed": self.patches_failed,
            "candidates": self.candidates,
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
            "proposals": [suggestion.to_dict() for suggestion in self.suggestions],
        }


def suggest_patches(
    project_path: Path | str,
    *,
    report_path: Path | str,
    max_patches: int | None = None,
    max_findings: int | None = None,
    output_dir: Path | str = "reports",
    dry_run: bool = False,
    client: OllamaClient | None = None,
) -> PatchSuggestionSummary:
    """Generate read-only patch suggestion files from existing findings."""
    limit = max_patches if max_patches is not None else (max_findings if max_findings is not None else 5)
    if limit < 1:
        raise ValueError("max_patches must be greater than 0")

    project_root = Path(project_path).expanduser().resolve(strict=True)
    if not project_root.is_dir():
        raise NotADirectoryError(f"project path is not a directory: {project_root}")

    resolved_report_path = Path(report_path).expanduser().resolve(strict=True)
    report = json.loads(resolved_report_path.read_text(encoding="utf-8"))
    findings = collect_actionable_findings(report)[:limit]
    patch_dir = Path(output_dir) / PATCHES_DIRNAME
    candidates = [candidate_summary(finding) for finding in findings]

    if dry_run:
        status = "no_findings" if not findings else "dry_run"
        return PatchSuggestionSummary(
            mode="suggest_patch",
            status=status,
            project_path=str(project_root),
            report_path=str(resolved_report_path),
            output_dir=str(patch_dir),
            warning=PATCH_WARNING,
            dry_run=True,
            findings_considered=len(findings),
            patches_created=0,
            patches_failed=0,
            candidates=candidates,
            suggestions=[],
        )

    patch_client = client or OllamaClient(load_ollama_config())
    suggestions: list[PatchSuggestion] = []
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for index, finding in enumerate(findings, start=1):
        suggestions.append(
            suggest_patch_for_finding(
                project_root=project_root,
                finding=finding,
                patch_dir=patch_dir,
                index=index,
                timestamp=timestamp,
                client=patch_client,
            )
        )

    patches_created = sum(1 for suggestion in suggestions if suggestion.status == "suggested")
    patches_failed = len(suggestions) - patches_created
    if not findings:
        status = "no_findings"
    elif patches_failed:
        status = "completed_with_errors"
    else:
        status = "completed"

    return PatchSuggestionSummary(
        mode="suggest_patch",
        status=status,
        project_path=str(project_root),
        report_path=str(resolved_report_path),
        output_dir=str(patch_dir.resolve() if patch_dir.exists() else patch_dir),
        warning=PATCH_WARNING,
        dry_run=False,
        findings_considered=len(findings),
        patches_created=patches_created,
        patches_failed=patches_failed,
        candidates=candidates,
        suggestions=suggestions,
    )


def collect_actionable_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect findings from audit JSON or task_results JSON."""
    findings: list[dict[str, Any]] = []

    if isinstance(report.get("findings"), dict):
        grouped = report["findings"]
        if isinstance(grouped.get("all"), list):
            findings.extend(_normalize_finding(item) for item in grouped["all"] if isinstance(item, dict))
        elif isinstance(grouped.get("by_risk"), dict):
            findings.extend(_collect_from_grouped(grouped["by_risk"]))

    if isinstance(report.get("findings_by_priority"), dict):
        findings.extend(_collect_from_grouped(report["findings_by_priority"]))

    if isinstance(report.get("results"), list):
        findings.extend(_collect_from_task_results(report["results"]))

    filtered = dedupe_findings(
        finding for finding in findings if finding.get("file") and finding.get("severity") in SEVERITY_ORDER
    )
    return sorted(filtered, key=lambda finding: SEVERITY_ORDER.index(finding["severity"]))


def dedupe_findings(findings: Any) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for finding in findings:
        key = (
            finding.get("file"),
            finding.get("line"),
            finding.get("type"),
            finding.get("severity"),
            finding.get("evidence"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _collect_from_grouped(grouped: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for severity in SEVERITY_ORDER:
        for finding in grouped.get(severity, []):
            if isinstance(finding, dict):
                normalized = _normalize_finding(finding)
                normalized.setdefault("severity", severity)
                findings.append(normalized)
    return findings


def _collect_from_task_results(results: list[Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        file_path = result.get("file_path")
        analysis = result.get("result")
        if not isinstance(analysis, dict) or not isinstance(analysis.get("findings"), list):
            continue
        for finding in analysis["findings"]:
            if isinstance(finding, dict):
                normalized = _normalize_finding(finding)
                normalized["file"] = str(normalized.get("file") or file_path or analysis.get("file") or "")
                findings.append(normalized)
    return findings


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    severity = str(finding.get("severity") or finding.get("risk") or "").lower()
    return {
        "file": str(finding.get("file") or finding.get("file_path") or ""),
        "line": finding.get("line"),
        "type": str(finding.get("type") or finding.get("finding_type") or ""),
        "severity": severity,
        "evidence": str(finding.get("evidence") or ""),
        "recommendation": str(finding.get("recommendation") or ""),
        "summary": str(finding.get("summary") or finding.get("evidence") or ""),
    }


def candidate_summary(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_path": str(finding.get("file", "")),
        "finding_type": str(finding.get("type", "")),
        "severity": str(finding.get("severity", "")),
        "line": finding.get("line"),
        "summary": str(finding.get("summary") or finding.get("evidence") or ""),
    }


def suggest_patch_for_finding(
    *,
    project_root: Path,
    finding: dict[str, Any],
    patch_dir: Path,
    index: int,
    timestamp: str,
    client: OllamaClient,
) -> PatchSuggestion:
    file_path = str(finding.get("file", ""))
    model = getattr(getattr(client, "config", None), "model", "")
    try:
        source_path = resolve_project_file(project_root, file_path)
        file_content = source_path.read_text(encoding="utf-8", errors="replace")
        max_chars = getattr(getattr(client, "config", None), "max_chars_per_file", 12000)
        bounded_content = file_content[:max_chars]
        prompt = render_patch_prompt(finding, bounded_content)
        raw_response = client.analyze_text_with_model(prompt, bounded_content)
        guarded = guard_json(raw_response, PATCH_SCHEMA_PATH)
        if not guarded.valid or not isinstance(guarded.data, dict):
            errors = guarded.errors or ["invalid patch suggestion JSON"]
            return failed_suggestion(file_path, finding, errors, model=model)

        data = dict(guarded.data)
        data["not_applied"] = True
        data.setdefault("errors", [])
        suggestion = build_suggestion_from_model_data(data, finding=finding, model=model)
        if suggestion.status == "suggested":
            validate_patch_for_file(suggestion.diff, project_root=project_root, file_path=file_path)
        markdown_path, json_path = write_patch_outputs(
            patch_dir=patch_dir,
            timestamp=timestamp,
            index=index,
            suggestion=suggestion,
        )
        return PatchSuggestion(
            **{
                **asdict(suggestion),
                "patch_markdown": str(markdown_path.resolve()),
                "patch_json": str(json_path.resolve()),
            }
        )
    except (OSError, ValueError, OllamaError) as error:
        return failed_suggestion(file_path, finding, [str(error)], model=model)


def failed_suggestion(
    file_path: str,
    finding: dict[str, Any],
    errors: list[str],
    *,
    model: str = "",
) -> PatchSuggestion:
    severity = str(finding.get("severity", "low"))
    if severity not in SEVERITY_ORDER:
        severity = "low"
    return PatchSuggestion(
        status="failed",
        file_path=file_path,
        finding_type=str(finding.get("type", "")),
        severity=severity,
        summary=str(finding.get("summary") or finding.get("evidence") or "Patch suggestion failed."),
        diff="",
        not_applied=True,
        errors=errors,
        model=model,
        finding=finding,
    )


def build_suggestion_from_model_data(
    data: dict[str, Any],
    *,
    finding: dict[str, Any],
    model: str,
) -> PatchSuggestion:
    status = str(data.get("status", "failed"))
    if status not in {"suggested", "failed"}:
        status = "failed"
    return PatchSuggestion(
        status=status,
        file_path=str(data.get("file_path") or finding.get("file") or ""),
        finding_type=str(data.get("finding_type") or finding.get("type") or ""),
        severity=str(data.get("severity") or finding.get("severity") or "low"),
        summary=str(data.get("summary") or ""),
        diff=str(data.get("diff") or ""),
        not_applied=True,
        errors=[str(error) for error in data.get("errors", [])],
        model=model,
        finding=finding,
    )


def resolve_project_file(project_root: Path, file_path: str) -> Path:
    normalized = normalize_project_path(file_path)
    candidate = project_root / normalized
    if not candidate.exists():
        raise ValueError(f"finding file not found: {file_path}")
    resolved = candidate.resolve(strict=True)
    if not _is_relative_to(resolved, project_root):
        raise ValueError(f"finding file escapes project root: {file_path}")
    if not resolved.is_file():
        raise ValueError(f"finding file is not a file: {file_path}")
    return resolved


def normalize_project_path(file_path: str) -> str:
    if file_path.strip() == "":
        raise ValueError("finding does not include a file path")
    normalized = file_path.strip().strip('"').replace("\\", "/")
    if normalized.startswith(("a/", "b/")):
        normalized = normalized[2:]
    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts or (pure_path.parts and ":" in pure_path.parts[0]):
        raise ValueError(f"unsafe project file path: {file_path}")
    return pure_path.as_posix()


def render_patch_prompt(finding: dict[str, Any], file_content: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    replacements = {
        "file_path": str(finding.get("file", "")),
        "finding_type": str(finding.get("type", "")),
        "severity": str(finding.get("severity", "")),
        "line": str(finding.get("line", "")),
        "evidence": str(finding.get("evidence", "")),
        "recommendation": str(finding.get("recommendation", "")),
        "file_content": file_content,
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def validate_patch_for_file(diff_text: str, *, project_root: Path, file_path: str) -> None:
    if diff_text.strip() == "":
        raise ValueError("patch proposal is empty")

    expected = normalize_diff_path(file_path)
    diff_paths = extract_diff_paths(diff_text)
    if not diff_paths:
        raise ValueError("patch proposal does not include unified diff file headers")

    for diff_path in diff_paths:
        normalized = normalize_diff_path(diff_path)
        if normalized != expected:
            raise ValueError(f"patch touches unexpected file: {diff_path}")
        resolved = (project_root / normalized).resolve(strict=False)
        if not _is_relative_to(resolved, project_root):
            raise ValueError(f"patch path escapes project root: {diff_path}")


def extract_diff_paths(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            paths.extend(parts[2:4])
        elif line.startswith("--- ") or line.startswith("+++ "):
            path = line[4:].split("\t", 1)[0].strip()
            if path != "/dev/null":
                paths.append(path)
    return paths


def normalize_diff_path(path: str) -> str:
    normalized = path.strip().strip('"').replace("\\", "/")
    if normalized.startswith(("a/", "b/")):
        normalized = normalized[2:]
    if normalized.startswith("./"):
        normalized = normalized[2:]

    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts or (pure_path.parts and ":" in pure_path.parts[0]):
        raise ValueError(f"unsafe patch path: {path}")
    return pure_path.as_posix()


def write_patch_outputs(
    *,
    patch_dir: Path,
    timestamp: str,
    index: int,
    suggestion: PatchSuggestion,
) -> tuple[Path, Path]:
    patch_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if index == 1 else f"-{index:03d}"
    base_path = unique_path(patch_dir / f"patch-{timestamp}{suffix}")
    markdown_path = base_path.with_suffix(".md")
    json_path = base_path.with_suffix(".json")

    json_data = suggestion.to_dict()
    json_data["created_at"] = datetime.now(timezone.utc).isoformat()
    json_data["warning"] = PATCH_WARNING
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_patch_markdown(json_data), encoding="utf-8")
    return markdown_path, json_path


def render_patch_markdown(data: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# LocalScope Patch Suggestion",
            "",
            f"Status: {data.get('status', '')}",
            f"File: {data.get('file_path', '')}",
            f"Severity: {data.get('severity', '')}",
            f"Finding: {data.get('finding_type', '')}",
            f"Model: {data.get('model', '') or '-'}",
            f"Warning: {PATCH_WARNING}",
            "",
            "## Summary",
            "",
            str(data.get("summary", "")),
            "",
            "## Diff",
            "",
            "```diff",
            str(data.get("diff", "")).rstrip(),
            "```",
            "",
            "## Errors",
            "",
            *(f"- {error}" for error in data.get("errors", [])),
            "",
        ]
    )


def unique_path(base_path: Path) -> Path:
    if not base_path.with_suffix(".json").exists() and not base_path.with_suffix(".md").exists():
        return base_path
    for index in range(1, 1000):
        candidate = base_path.with_name(f"{base_path.name}-{index}")
        if not candidate.with_suffix(".json").exists() and not candidate.with_suffix(".md").exists():
            return candidate
    raise FileExistsError(f"could not create a unique patch path for {base_path}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
