"""CLI wrapper for the high-level OpenClaw adapter tool for LocalScope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.openclaw.local_scope_audit import local_scope_audit  # noqa: E402


local_project_audit = local_scope_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only LocalScope audit for OpenClaw.")
    parser.add_argument("--path", required=True, help="project folder to audit")
    parser.add_argument(
        "--profile",
        default="auto",
        help="auto, general, php, wordpress, javascript, python, java, or docker",
    )
    parser.add_argument(
        "--mode",
        default="general",
        help="general, security, or code_quality",
    )
    parser.add_argument("--max-tasks", type=int, default=5, help="maximum pending tasks to process")
    parser.add_argument("--use-memory", default="true", help="true or false")
    parser.add_argument("--use-graphify", default="true", help="true or false")
    parser.add_argument(
        "--read-only",
        default="true",
        help="must be true; editing is not supported",
    )
    parser.add_argument("--output-dir", default="reports", help="where governor reports are written")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        response = local_project_audit(
            path=Path(args.path),
            profile=args.profile,
            mode=args.mode,
            max_tasks=args.max_tasks,
            use_memory=parse_bool(args.use_memory),
            use_graphify=parse_bool(args.use_graphify),
            read_only=parse_bool(args.read_only),
            output_dir=Path(args.output_dir),
        )
    except Exception as error:  # noqa: BLE001 - wrapper must return JSON for OpenClaw.
        response = error_response(path=args.path, error=error)

    print(json.dumps(response, indent=2))
    return 0 if response.get("status") == "completed" else 1


def parse_bool(value: Any) -> bool:
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
