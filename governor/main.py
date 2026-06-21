"""Command line entry point for Claw Local Task Governor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from governor.ollama_client import OllamaError, analyze_text_with_model
from governor.openclaw_tool import local_audit_report, local_audit_status, local_project_audit
from governor.patch_suggester import suggest_patches
from governor.reducer import build_final_report, load_audit_inputs
from governor.report_writer import write_audit_reports
from governor.scanner import scan_project
from governor.task_queue import generate_tasks_from_scan_result
from governor.task_runner import run_pending_tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claw-local-task-governor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan a project folder read-only")
    scan_parser.add_argument("path", help="project folder to scan")
    scan_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory where scan_result.json will be written",
    )

    tasks_parser = subparsers.add_parser(
        "tasks",
        help="generate pending microtasks from scanner output",
    )
    tasks_parser.add_argument("path", help="project folder to scan and queue")
    tasks_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory where scan_result.json and tasks.json will be written",
    )

    subparsers.add_parser(
        "ollama-test",
        help="send a small test message to the configured local Ollama model",
    )

    run_tasks_parser = subparsers.add_parser(
        "run-tasks",
        help="run a limited number of pending tasks with Ollama",
    )
    run_tasks_parser.add_argument("path", help="project folder containing files to analyze")
    run_tasks_parser.add_argument(
        "--max-tasks",
        type=int,
        required=True,
        help="maximum number of pending tasks to run",
    )
    run_tasks_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory containing tasks.json and receiving task_results.json",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="reduce task results into final Markdown and JSON reports",
    )
    report_parser.add_argument("path", help="project folder for report metadata")
    report_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory containing scan/task results and receiving audit reports",
    )

    openclaw_parser = subparsers.add_parser(
        "openclaw-audit",
        help="run the single high-level read-only OpenClaw audit tool",
    )
    openclaw_parser.add_argument("--path", required=True, help="project folder to audit")
    openclaw_parser.add_argument(
        "--profile",
        default="auto",
        help="auto, general, php, wordpress, javascript, python, java, or docker",
    )
    openclaw_parser.add_argument(
        "--mode",
        default="general",
        help="general, security, code_quality, performance, or seo",
    )
    openclaw_parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="maximum number of files/tasks to analyze with the model",
    )
    openclaw_parser.add_argument(
        "--read-only",
        choices=["true", "false"],
        default="true",
        help="must be true; editing is not supported",
    )
    openclaw_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory for scan, task, result, and final report files",
    )

    openclaw_status_parser = subparsers.add_parser(
        "openclaw-status",
        help="return recent local audit status without reanalyzing files",
    )
    openclaw_status_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory containing audit reports and task_results.json",
    )
    openclaw_status_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="maximum number of recent audits to return",
    )

    openclaw_report_parser = subparsers.add_parser(
        "openclaw-report",
        help="return a compact summary for an existing audit report",
    )
    openclaw_report_parser.add_argument(
        "--report-path",
        required=True,
        help="path to audit-*.json or audit-*.md",
    )

    suggest_patch_parser = subparsers.add_parser(
        "suggest-patch",
        help="generate reviewable patch proposals from existing findings without applying them",
    )
    suggest_patch_parser.add_argument("path", help="project folder containing files referenced by findings")
    suggest_patch_parser.add_argument(
        "--report-path",
        required=True,
        help="path to an existing audit JSON report",
    )
    suggest_patch_parser.add_argument(
        "--max-findings",
        type=int,
        default=5,
        help="maximum number of actionable findings to propose patches for",
    )
    suggest_patch_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory where reports/patches proposals will be written",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        result = scan_project(Path(args.path), output_dir=Path(args.output_dir))
        output_path = Path(args.output_dir) / "scan_result.json"
        print("Scan completed.")
        print(f"Files found: {result.files_found}")
        print(f"Files ignored: {result.files_ignored}")
        print(f"Relevant files: {result.relevant_files}")
        print(f"Detected profile: {result.profile_detected}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "tasks":
        scan_project(Path(args.path), output_dir=Path(args.output_dir))
        scan_result_path = Path(args.output_dir) / "scan_result.json"
        queue = generate_tasks_from_scan_result(
            scan_result_path,
            output_dir=Path(args.output_dir),
        )
        output_path = Path(args.output_dir) / "tasks.json"
        print("Task queue generated.")
        print(f"Tasks created: {queue.tasks_total}")
        print(f"Tasks pending: {queue.tasks_pending}")
        print(f"Profile: {queue.profile}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "ollama-test":
        try:
            response = analyze_text_with_model(
                "Reply with one short plain sentence.",
                "Say that the local Ollama connection works.",
            )
        except OllamaError as error:
            print(f"Ollama test failed: {error}")
            return 1

        print("Ollama test completed.")
        print(response.strip())
        return 0

    if args.command == "run-tasks":
        try:
            summary = run_pending_tasks(
                Path(args.path),
                max_tasks=args.max_tasks,
                output_dir=Path(args.output_dir),
            )
        except (OSError, ValueError) as error:
            print(f"Task run failed: {error}")
            return 1

        output_path = Path(args.output_dir) / "task_results.json"
        print("Task run completed.")
        print(f"Tasks selected: {summary.tasks_selected}")
        print(f"Tasks new: {summary.tasks_new}")
        print(f"Tasks reused: {summary.tasks_reused}")
        print(f"Tasks completed: {summary.tasks_completed}")
        print(f"Tasks failed: {summary.tasks_failed}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "report":
        inputs = load_audit_inputs(Path(args.path), output_dir=Path(args.output_dir))
        report = build_final_report(inputs)
        markdown_path, json_path = write_audit_reports(report, output_dir=Path(args.output_dir))
        print("Report generated.")
        print(f"Markdown: {markdown_path.as_posix()}")
        print(f"JSON: {json_path.as_posix()}")
        return 0

    if args.command == "openclaw-audit":
        try:
            response = local_project_audit(
                path=Path(args.path),
                profile=args.profile,
                mode=args.mode,
                max_files=args.max_files,
                read_only=parse_bool(args.read_only),
                output_dir=Path(args.output_dir),
            )
        except (OSError, ValueError) as error:
            response = {
                "status": "failed",
                "report_path": "",
                "summary": str(error),
                "files_scanned": 0,
                "files_analyzed": 0,
                "files_reused_from_memory": 0,
                "json_valid": 0,
                "json_repaired": 0,
                "json_failed": 0,
            }
            print(json.dumps(response, indent=2))
            return 1

        print(json.dumps(response, indent=2))
        return 0

    if args.command == "openclaw-status":
        try:
            response = local_audit_status(output_dir=Path(args.output_dir), limit=args.limit)
        except ValueError as error:
            response = {"status": "failed", "summary": str(error), "recent_audits": []}
            print(json.dumps(response, indent=2))
            return 1

        print(json.dumps(response, indent=2))
        return 0

    if args.command == "openclaw-report":
        try:
            response = local_audit_report(report_path=Path(args.report_path))
        except (OSError, ValueError) as error:
            response = {
                "status": "failed",
                "report_path": "",
                "json_report_path": "",
                "summary": str(error),
            }
            print(json.dumps(response, indent=2))
            return 1

        print(json.dumps(response, indent=2))
        return 0

    if args.command == "suggest-patch":
        try:
            summary = suggest_patches(
                Path(args.path),
                report_path=Path(args.report_path),
                max_findings=args.max_findings,
                output_dir=Path(args.output_dir),
            )
        except (OSError, ValueError) as error:
            response = {
                "mode": "suggest_patch",
                "status": "failed",
                "summary": str(error),
                "warning": "Propuesta no aplicada automáticamente.",
                "patches_created": 0,
            }
            print(json.dumps(response, indent=2))
            return 1

        print(json.dumps(summary.to_dict(), indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def parse_bool(value: str) -> bool:
    return str(value).lower() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
