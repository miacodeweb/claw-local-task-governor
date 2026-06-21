"""Generate reviewable patch proposals without applying them."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from governor.ollama_client import OllamaClient, OllamaError, load_ollama_config


PATCH_WARNING = "Propuesta no aplicada automáticamente."
PATCHES_DIRNAME = "patches"
PROMPT_PATH = Path("prompts") / "suggest_patch.txt"
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class PatchProposal:
    file: str
    severity: str
    finding_type: str
    status: str
    patch_path: str
    warning: str
    errors: list[str]


@dataclass(frozen=True)
class PatchSuggestionSummary:
    mode: str
    status: str
    project_path: str
    report_path: str
    output_dir: str
    warning: str
    findings_considered: int
    patches_created: int
    patches_failed: int
    proposals: list[PatchProposal]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "project_path": self.project_path,
            "report_path": self.report_path,
            "output_dir": self.output_dir,
            "warning": self.warning,
            "findings_considered": self.findings_considered,
            "patches_created": self.patches_created,
            "patches_failed": self.patches_failed,
            "proposals": [asdict(proposal) for proposal in self.proposals],
        }


def suggest_patches(
    project_path: Path | str,
    *,
    report_path: Path | str,
    max_findings: int = 5,
    output_dir: Path | str = "reports",
    client: OllamaClient | None = None,
) -> PatchSuggestionSummary:
    """Generate patch proposal files from existing audit findings only."""
    if max_findings < 1:
        raise ValueError("max_findings must be greater than 0")

    project_root = Path(project_path).expanduser().resolve(strict=True)
    if not project_root.is_dir():
        raise NotADirectoryError(f"project path is not a directory: {project_root}")

    resolved_report_path = Path(report_path).expanduser().resolve(strict=True)
    report = json.loads(resolved_report_path.read_text(encoding="utf-8"))
    findings = collect_actionable_findings(report)[:max_findings]
    output_path = Path(output_dir)
    patch_dir = output_path / PATCHES_DIRNAME
    patch_client = client or OllamaClient(load_ollama_config())
    proposals: list[PatchProposal] = []

    for index, finding in enumerate(findings, start=1):
        proposals.append(
            suggest_patch_for_finding(
                project_root=project_root,
                finding=finding,
                patch_dir=patch_dir,
                index=index,
                client=patch_client,
            )
        )

    patches_created = sum(1 for proposal in proposals if proposal.status == "created")
    patches_failed = len(proposals) - patches_created
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
        output_dir=str(patch_dir.resolve()),
        warning=PATCH_WARNING,
        findings_considered=len(findings),
        patches_created=patches_created,
        patches_failed=patches_failed,
        proposals=proposals,
    )


def collect_actionable_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    grouped = report.get("findings_by_priority", {})
    for severity in SEVERITY_ORDER:
        for finding in grouped.get(severity, []):
            if isinstance(finding, dict) and finding.get("file"):
                findings.append(finding)
    return findings


def suggest_patch_for_finding(
    *,
    project_root: Path,
    finding: dict[str, Any],
    patch_dir: Path,
    index: int,
    client: OllamaClient,
) -> PatchProposal:
    file_path = str(finding.get("file", ""))
    try:
        source_path = resolve_project_file(project_root, file_path)
        file_content = source_path.read_text(encoding="utf-8", errors="replace")
        prompt = render_patch_prompt(finding, file_content)
        raw_diff = client.analyze_text_with_model(prompt, file_content)
        diff_text = clean_patch_text(raw_diff)
        validate_patch_for_file(diff_text, project_root=project_root, file_path=file_path)
        patch_path = write_patch_file(
            patch_dir=patch_dir,
            file_path=file_path,
            index=index,
            diff_text=diff_text,
            finding=finding,
        )
        return PatchProposal(
            file=file_path,
            severity=str(finding.get("severity", "")),
            finding_type=str(finding.get("type", "")),
            status="created",
            patch_path=str(patch_path.resolve()),
            warning=PATCH_WARNING,
            errors=[],
        )
    except (OSError, ValueError, OllamaError) as error:
        return PatchProposal(
            file=file_path,
            severity=str(finding.get("severity", "")),
            finding_type=str(finding.get("type", "")),
            status="failed",
            patch_path="",
            warning=PATCH_WARNING,
            errors=[str(error)],
        )


def resolve_project_file(project_root: Path, file_path: str) -> Path:
    if file_path.strip() == "":
        raise ValueError("finding does not include a file path")
    candidate = project_root / file_path
    if not candidate.exists():
        raise ValueError(f"finding file not found: {file_path}")
    resolved = candidate.resolve(strict=True)
    if not _is_relative_to(resolved, project_root):
        raise ValueError(f"finding file escapes project root: {file_path}")
    if not resolved.is_file():
        raise ValueError(f"finding file is not a file: {file_path}")
    return resolved


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


def clean_patch_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text + "\n"


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


def write_patch_file(
    *,
    patch_dir: Path,
    file_path: str,
    index: int,
    diff_text: str,
    finding: dict[str, Any],
) -> Path:
    patch_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_file = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_path.replace("\\", "/")).strip("_")
    base_name = f"{timestamp}-{index:03d}-{safe_file or 'patch'}.diff"
    patch_path = unique_path(patch_dir / base_name)
    header = "\n".join(
        [
            PATCH_WARNING,
            f"File: {file_path}",
            f"Severity: {finding.get('severity', '')}",
            f"Type: {finding.get('type', '')}",
            "",
        ]
    )
    patch_path.write_text(header + diff_text, encoding="utf-8")
    return patch_path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not create a unique patch path for {path}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
