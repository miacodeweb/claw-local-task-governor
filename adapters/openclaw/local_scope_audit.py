"""OpenClaw-facing LocalScope audit adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.common.audit_request import AuditRequest  # noqa: E402
from adapters.common.run_audit import run_audit  # noqa: E402
from governor.memory import SQLiteMemory  # noqa: E402
from governor.ollama_client import OllamaClient  # noqa: E402


def local_scope_audit(
    *,
    path: Path | str,
    profile: str = "auto",
    mode: str = "general",
    max_tasks: int | None = None,
    max_files: int | None = None,
    use_memory: bool = True,
    use_graphify: bool = True,
    read_only: bool = True,
    output_dir: Path | str = "reports",
    client: OllamaClient | None = None,
    memory: SQLiteMemory | None = None,
) -> dict[str, Any]:
    """Run the high-level read-only LocalScope audit flow for OpenClaw."""
    task_limit = max_tasks if max_tasks is not None else (max_files if max_files is not None else 5)
    request = AuditRequest.from_dict(
        {
            "path": str(path),
            "profile": profile,
            "mode": mode,
            "max_tasks": task_limit,
            "use_memory": use_memory,
            "use_graphify": use_graphify,
            "read_only": read_only,
        }
    )
    return run_audit(
        request,
        adapter="openclaw",
        output_dir=output_dir,
        client=client,
        memory=memory,
    ).to_dict()


def local_project_audit(**kwargs: Any) -> dict[str, Any]:
    """Compatibility alias for older OpenClaw configurations."""
    return local_scope_audit(**kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LocalScope as a read-only OpenClaw tool.")
    parser.add_argument("--path", required=True, help="project folder to audit")
    parser.add_argument(
        "--profile",
        default="auto",
        help="auto, general, php, wordpress, javascript, python, java, docker, config_files, windows_folder, linux_folder, or documentation",
    )
    parser.add_argument(
        "--mode",
        default="general",
        help="general, security, code_quality, or config_audit",
    )
    parser.add_argument("--max-tasks", type=int, default=5, help="maximum pending tasks to process")
    parser.add_argument("--use-memory", default="true", help="true or false")
    parser.add_argument("--use-graphify", default="true", help="true or false")
    parser.add_argument(
        "--read-only",
        default="true",
        help="must be true; editing is not supported",
    )
    parser.add_argument("--output-dir", default="reports", help="where LocalScope reports are written")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        response = local_scope_audit(
            path=Path(args.path),
            profile=args.profile,
            mode=args.mode,
            max_tasks=args.max_tasks,
            use_memory=parse_bool(args.use_memory),
            use_graphify=parse_bool(args.use_graphify),
            read_only=parse_bool(args.read_only),
            output_dir=Path(args.output_dir),
        )
    except Exception as error:  # noqa: BLE001 - OpenClaw must always receive JSON.
        response = error_response(path=args.path, error=error)

    sys.stdout.write(json.dumps(response, indent=2))
    sys.stdout.write("\n")
    return 0 if response.get("status") == "completed" else 1


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def error_response(*, path: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "adapter": "openclaw",
        "project_path": str(path),
        "profile_detected": "",
        "report_markdown": "",
        "report_json": "",
        "tasks_processed": 0,
        "reused": 0,
        "json_valid": 0,
        "json_repaired": 0,
        "json_failed": 0,
        "summary": str(error),
        "errors": [str(error)],
    }


if __name__ == "__main__":
    raise SystemExit(main())
