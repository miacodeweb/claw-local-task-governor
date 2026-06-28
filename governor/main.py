"""Command line entry point for LocalScope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters.common.run_audit import run_audit
from governor.adaptive_limits import load_adaptive_limits_config, recommendations_for_profiles
from governor.graphify_adapter import get_graph_summary
from governor.logging_manager import get_log_manager, read_log_errors, read_log_summary, read_log_tasks
from governor.memory import DEFAULT_MEMORY_PATH
from governor.model_benchmark import (
    BenchmarkDryRun,
    BenchmarkReport,
    DEFAULT_BENCHMARK_OUTPUT_DIR,
    ModelBenchmarkStats,
    run_benchmark,
)
from governor.model_profiles import ModelProfileStore
from governor.model_recommendations import get_model_recommendations
from governor.profile_benchmark import (
    ProfileBenchmarkReport,
    run_profile_benchmark,
)
from governor.ollama_client import OllamaClient, OllamaError, load_ollama_config, list_models as ollama_list_models
from governor.openclaw_tool import local_audit_report, local_audit_status, local_project_audit
from governor.patch_suggester import suggest_patches
from governor.prompt_manager import list_prompt_variants, recommend_prompt
from governor.reducer import build_final_report, load_audit_inputs
from governor.report_writer import write_audit_reports
from governor.scanner import scan_project
from governor.task_queue import generate_tasks_from_scan_result
from governor.task_runner import run_pending_tasks


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localscope")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="run the full read-only LocalScope audit flow",
    )
    audit_parser.add_argument("path", help="project folder to audit")
    audit_parser.add_argument(
        "--profile",
        default="auto",
        help="auto, general, php, wordpress, javascript, python, java, docker, config_files, windows_folder, linux_folder, or documentation",
    )
    audit_parser.add_argument(
        "--mode",
        default="general",
        help="general, security, code_quality, or config_audit",
    )
    audit_parser.add_argument(
        "--max-tasks",
        type=int,
        default=5,
        help="maximum pending tasks to process",
    )
    memory_group = audit_parser.add_mutually_exclusive_group()
    memory_group.add_argument(
        "--use-memory",
        dest="use_memory",
        action="store_true",
        default=True,
        help="reuse SQLite memory when possible",
    )
    memory_group.add_argument(
        "--no-memory",
        dest="use_memory",
        action="store_false",
        help="ignore reusable SQLite memory for this audit",
    )
    graphify_group = audit_parser.add_mutually_exclusive_group()
    graphify_group.add_argument(
        "--use-graphify",
        dest="use_graphify",
        action="store_true",
        default=True,
        help="use existing Graphify output when available",
    )
    graphify_group.add_argument(
        "--no-graphify",
        dest="use_graphify",
        action="store_false",
        help="ignore Graphify output for this audit",
    )
    audit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scan and plan tasks without calling Ollama or writing model results",
    )
    audit_parser.add_argument(
        "--no-adaptive-limits",
        dest="use_adaptive_limits",
        action="store_false",
        default=True,
        help="use the fixed ollama.max_chars_per_file value instead of model profile recommendations",
    )
    audit_parser.add_argument(
        "--prompt-version",
        default=None,
        help="force a known prompt version such as v1, v2_strict_json, or v3_short_schema",
    )
    audit_parser.add_argument(
        "--read-only",
        choices=["true", "false"],
        default="true",
        help="must be true; editing is not supported",
    )
    audit_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory for scan, task, result, and final report files",
    )
    audit_parser.add_argument(
        "--model",
        default=None,
        help="override the Ollama model name (takes priority over config.yaml and benchmark recommendations)",
    )
    audit_parser.add_argument(
        "--use-benchmark-recommendations",
        action="store_true",
        help="select model from benchmark results when available",
    )

    scan_parser = subparsers.add_parser("scan", help="scan a project folder read-only")
    scan_parser.add_argument("path", help="project folder to scan")
    scan_parser.add_argument(
        "--profile",
        default="auto",
        help="force a project profile instead of auto detection",
    )
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
        "--profile",
        default="auto",
        help="force a project profile instead of auto detection",
    )
    tasks_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory where scan_result.json and tasks.json will be written",
    )

    subparsers.add_parser(
        "ollama-test",
        help="send a small test message to the configured local Ollama model",
    )

    graphify_parser = subparsers.add_parser(
        "graphify-info",
        help="show optional Graphify output diagnostics without running Graphify",
    )
    graphify_parser.add_argument("path", help="project folder to inspect for graphify-out artifacts")

    run_tasks_parser = subparsers.add_parser(
        "run-tasks",
        help="run a limited number of pending tasks with Ollama",
    )
    run_tasks_parser.add_argument("path", help="project folder containing files to analyze")
    run_tasks_parser.add_argument(
        "--profile",
        default="auto",
        help="force task profile for prompt rendering; auto keeps tasks.json values",
    )
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
    run_tasks_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show pending tasks and prompt previews without calling Ollama or writing task_results.json",
    )
    run_tasks_parser.add_argument(
        "--no-memory",
        action="store_true",
        help="ignore reusable SQLite task results and process selected tasks again",
    )
    run_tasks_parser.add_argument(
        "--no-adaptive-limits",
        action="store_true",
        help="use the fixed ollama.max_chars_per_file value instead of model profile recommendations",
    )
    run_tasks_parser.add_argument(
        "--prompt-version",
        default=None,
        help="force a known prompt version such as v1, v2_strict_json, or v3_short_schema",
    )
    run_tasks_parser.add_argument(
        "--model",
        default=None,
        help="override the Ollama model name",
    )
    run_tasks_parser.add_argument(
        "--use-benchmark-recommendations",
        action="store_true",
        help="select model from benchmark results when available",
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
    report_parser.add_argument(
        "--results",
        default=None,
        help="path to task_results.json; defaults to <output-dir>/task_results.json",
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
        help="general, security, or code_quality",
    )
    openclaw_parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="maximum number of files/tasks to analyze with the model",
    )
    openclaw_parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="legacy alias for --max-tasks",
    )
    openclaw_parser.add_argument(
        "--use-memory",
        choices=["true", "false"],
        default="true",
        help="whether to reuse SQLite task memory",
    )
    openclaw_parser.add_argument(
        "--use-graphify",
        choices=["true", "false"],
        default="true",
        help="whether to use existing Graphify output as optional context",
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
        "--report",
        dest="report_path",
        help="path to an existing audit JSON report or task_results.json",
    )
    suggest_patch_parser.add_argument(
        "--report-path",
        dest="report_path",
        help="path to an existing audit JSON report or task_results.json",
    )
    suggest_patch_parser.add_argument(
        "--max-patches",
        dest="max_patches",
        type=int,
        default=5,
        help="maximum number of actionable findings to propose patches for",
    )
    suggest_patch_parser.add_argument(
        "--max-findings",
        dest="max_patches",
        type=int,
        help="maximum number of actionable findings to propose patches for",
    )
    suggest_patch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show patch candidates without calling Ollama or writing proposal files",
    )
    suggest_patch_parser.add_argument(
        "--output-dir",
        default="reports",
        help="directory where reports/patches proposals will be written",
    )

    model_stats_parser = subparsers.add_parser(
        "model-stats",
        help="show operational LocalScope metrics for local model behavior",
    )
    model_stats_parser.add_argument(
        "--model",
        default=None,
        help="filter stats by model name",
    )
    model_stats_parser.add_argument(
        "--task-type",
        default=None,
        help="filter stats by task type",
    )
    model_stats_parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON",
    )
    model_stats_parser.add_argument(
        "--recommendations",
        action="store_true",
        help="include adaptive max_chars recommendations",
    )

    rec_parser = subparsers.add_parser(
        "model-recommendations",
        help="show recommended model, prompt, and limits from benchmark data",
    )
    rec_parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON",
    )
    rec_parser.add_argument(
        "--task-type",
        default=None,
        help="filter recommendations by task type",
    )
    rec_parser.add_argument(
        "--profile",
        default="general",
        help="filter recommendations by project profile",
    )
    rec_parser.add_argument(
        "--latest-benchmark",
        action="store_true",
        help="prioritize the most recent benchmark report",
    )
    rec_parser.add_argument(
        "--include-demo-models",
        action="store_true",
        help="include demo/test/mock model names in recommendations for debugging",
    )

    prompts_parser = subparsers.add_parser(
        "prompts",
        help="inspect controlled prompt variants",
    )
    prompt_subparsers = prompts_parser.add_subparsers(dest="prompts_command", required=True)
    prompt_subparsers.add_parser("list", help="list available prompt variants")
    prompt_recommend_parser = prompt_subparsers.add_parser(
        "recommend",
        help="recommend a prompt version from model profile metrics",
    )
    prompt_recommend_parser.add_argument("--model", required=True, help="model name")
    prompt_recommend_parser.add_argument("--task-type", required=True, help="task type")
    prompt_recommend_parser.add_argument("--profile", default="general", help="project profile")
    prompt_recommend_parser.add_argument("--json", action="store_true", help="print JSON")

    benchmark_parser = subparsers.add_parser(
        "benchmark-models",
        help="compare installed Ollama models on a project fixture",
    )
    benchmark_parser.add_argument("path", help="project folder to use as benchmark fixture")
    benchmark_parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="list of model names to benchmark (e.g. qwen2.5-coder:7b gemma4:12b)",
    )
    benchmark_parser.add_argument(
        "--all-ollama",
        action="store_true",
        help="benchmark all installed Ollama models (does not download)",
    )
    benchmark_parser.add_argument(
        "--max-tasks",
        type=int,
        default=5,
        help="maximum files/tasks per model",
    )
    benchmark_parser.add_argument(
        "--profile",
        default="auto",
        help="auto, general, php, wordpress, javascript, python, java, docker, config_files, windows_folder, linux_folder, or documentation",
    )
    benchmark_parser.add_argument(
        "--mode",
        default="general",
        help="general, security, code_quality, or config_audit",
    )
    benchmark_parser.add_argument(
        "--prompt-versions",
        nargs="*",
        default=None,
        help="prompt versions to test (e.g. v1 v2_strict_json v3_short_schema)",
    )
    benchmark_parser.add_argument(
        "--no-adaptive-limits",
        action="store_true",
        help="use fixed max_chars_per_file instead of adaptive limits",
    )
    benchmark_parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=None,
        help="override Ollama timeout per request; local models may need 240-360 seconds",
    )
    benchmark_parser.add_argument(
        "--delay-between-models",
        type=_non_negative_int,
        default=0,
        help="seconds to wait between models so Ollama can recover",
    )
    benchmark_parser.add_argument(
        "--output-dir",
        default="reports/benchmarks",
        help="directory for benchmark output",
    )
    benchmark_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show models and tasks without calling Ollama",
    )

    profile_bench_parser = subparsers.add_parser(
        "benchmark-profile",
        help="compare models per project profile using calibration fixtures",
    )
    profile_bench_parser.add_argument(
        "profile",
        nargs="+",
        help="profile(s) to benchmark: python, javascript, java, php, wordpress, docker, config_files, windows_folder, linux_folder, documentation, general, or all",
    )
    profile_bench_parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="list of model names to benchmark",
    )
    profile_bench_parser.add_argument(
        "--all-ollama",
        action="store_true",
        help="benchmark all installed Ollama models",
    )
    profile_bench_parser.add_argument(
        "--max-tasks",
        type=int,
        default=5,
        help="maximum files/tasks per model per profile",
    )
    profile_bench_parser.add_argument(
        "--prompt-versions",
        nargs="*",
        default=None,
        help="prompt versions to test (e.g. v1 v2_strict_json v3_short_schema)",
    )
    profile_bench_parser.add_argument(
        "--no-adaptive-limits",
        action="store_true",
        help="use fixed max_chars_per_file instead of adaptive limits",
    )
    profile_bench_parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=None,
        help="override Ollama timeout per request; local models may need 240-360 seconds",
    )
    profile_bench_parser.add_argument(
        "--delay-between-models",
        type=_non_negative_int,
        default=0,
        help="seconds to wait between models so Ollama can recover",
    )
    profile_bench_parser.add_argument(
        "--output-dir",
        default="reports/benchmarks",
        help="directory for benchmark output",
    )
    profile_bench_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show profiles, models, and tasks without calling Ollama",
    )

    calibrate_parser = subparsers.add_parser(
        "calibrate-models",
        help="warm-up and calibrate model recommendations per profile",
    )
    calibrate_parser.add_argument(
        "--profiles",
        nargs="+",
        default=["python", "javascript"],
        help="profiles to calibrate (e.g. python javascript config_files); use all for every profile",
    )
    calibrate_parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="list of model names to calibrate",
    )
    calibrate_parser.add_argument(
        "--all-ollama",
        action="store_true",
        help="calibrate all installed Ollama models",
    )
    calibrate_parser.add_argument(
        "--max-tasks",
        type=int,
        default=5,
        help="maximum files per model per profile",
    )
    calibrate_parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=None,
        help="override Ollama timeout per request; local models may need 240-360 seconds",
    )
    calibrate_parser.add_argument(
        "--delay-between-models",
        type=_non_negative_int,
        default=0,
        help="seconds to wait between models so Ollama can recover",
    )
    calibrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be calibrated without calling Ollama",
    )

    logs_parser = subparsers.add_parser(
        "logs",
        help="read structured log output",
    )
    logs_sub = logs_parser.add_subparsers(dest="logs_command", required=True)
    logs_sub.add_parser("summary", help="show summary of recent log activity")
    logs_errors = logs_sub.add_parser("errors", help="show recent error log entries")
    logs_errors.add_argument("--limit", type=int, default=20, help="max entries (default 20)")
    logs_tasks = logs_sub.add_parser("tasks", help="show recent task log entries")
    logs_tasks.add_argument("--limit", type=int, default=20, help="max entries (default 20)")

    webui_parser = subparsers.add_parser(
        "webui",
        help="start local read-only Web UI for reports, logs, and benchmarks",
    )
    webui_parser.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    webui_parser.add_argument("--port", type=int, default=8765, help="bind port (default 8765)")
    webui_parser.add_argument("--no-browser", action="store_true", help="do not open browser")

    prov_parser = subparsers.add_parser(
        "providers",
        help="list and inspect model providers",
    )
    prov_sub = prov_parser.add_subparsers(dest="providers_command", required=True)
    prov_sub.add_parser("list", help="list registered providers")
    prov_sub.add_parser("health", help="show health of all providers")
    prov_models = prov_sub.add_parser("models", help="list models for a provider")
    prov_models.add_argument("--provider", default="ollama", help="provider name (default ollama)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        request = {
            "path": str(args.path),
            "profile": args.profile,
            "mode": args.mode,
            "max_tasks": args.max_tasks,
            "use_memory": args.use_memory,
            "use_graphify": args.use_graphify,
            "use_adaptive_limits": args.use_adaptive_limits,
            "prompt_version": args.prompt_version,
            "read_only": parse_bool(args.read_only),
            "model_override": args.model if hasattr(args, "model") else None,
            "use_benchmark_recommendations": args.use_benchmark_recommendations if hasattr(args, "use_benchmark_recommendations") else False,
        }
        response = run_audit(
            request,
            adapter="cli",
            output_dir=Path(args.output_dir),
            dry_run=args.dry_run,
        ).to_dict()
        print_audit_response(response, dry_run=args.dry_run, output_dir=Path(args.output_dir))
        return 0 if response.get("status") == "completed" else 1

    if args.command == "scan":
        try:
            result = scan_project(Path(args.path), output_dir=Path(args.output_dir), profile=args.profile)
        except ValueError as error:
            print(f"Scan failed: {error}")
            return 1
        output_path = Path(args.output_dir) / "scan_result.json"
        print("Scan completed.")
        print(f"Files found: {result.files_found}")
        print(f"Files ignored: {result.files_ignored}")
        print(f"Relevant files: {result.relevant_files}")
        print(f"Detected profile: {result.profile_detected}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "tasks":
        try:
            scan_project(Path(args.path), output_dir=Path(args.output_dir), profile=args.profile)
        except ValueError as error:
            print(f"Task queue failed: {error}")
            return 1
        scan_result_path = Path(args.output_dir) / "scan_result.json"
        queue = generate_tasks_from_scan_result(
            scan_result_path,
            output_dir=Path(args.output_dir),
        )
        output_path = Path(args.output_dir) / "tasks.json"
        print("Task queue generated.")
        print(f"Tasks created: {queue.tasks_total}")
        print(f"Tasks pending: {queue.tasks_pending}")
        print(f"Tasks with Graphify signal: {queue.tasks_with_graphify_signal}")
        print("Tasks by priority:")
        for priority in ("high", "medium", "low"):
            print(f"- {priority}: {queue.tasks_by_priority.get(priority, 0)}")
        print(f"Profile: {queue.profile}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "ollama-test":
        try:
            config = load_ollama_config()
            client = OllamaClient(config)
            client.check_ollama_available()
            models = client.list_models()
            response = client.analyze_text_with_model(
                "Reply with one short plain sentence.",
                "Say that the local Ollama connection works.",
            )
        except OllamaError as error:
            print(f"Ollama test failed: {error}")
            return 1

        print("Ollama test completed.")
        print(f"Base URL: {config.base_url}")
        print(f"Configured model: {config.model}")
        if models:
            print("Available models:")
            for model in models:
                marker = " (configured)" if model == config.model else ""
                print(f"- {model}{marker}")
        else:
            print("Available models: none reported by Ollama")
        if models and config.model not in models:
            print("Warning: configured model was not listed by Ollama.")
        print("Response:")
        print(response.strip())
        return 0

    if args.command == "graphify-info":
        summary = get_graph_summary(Path(args.path))
        print(f"Graphify detectado: {'si' if summary['available'] else 'no'}")
        print(f"graph.json: {summary['graph_json'] or '-'}")
        print(f"GRAPH_REPORT.md: {summary['graph_report'] or '-'}")
        print(f"graph.html: {summary['graph_html'] or '-'}")
        print(f"Nodos detectados: {summary['nodes_detected']}")
        print(f"Enlaces detectados: {summary['edges_detected']}")
        print(f"Archivos referenciados: {len(summary['referenced_files'])}")
        for file_path in summary["referenced_files"][:20]:
            print(f"- {file_path}")
        if len(summary["referenced_files"]) > 20:
            print(f"- ... {len(summary['referenced_files']) - 20} mas")
        print(f"Archivos importantes: {len(summary.get('important_files', []))}")
        for file_path in summary.get("important_files", [])[:10]:
            print(f"- important: {file_path}")
        print(f"Nodos centrales: {len(summary.get('central_nodes', []))}")
        for node in summary.get("central_nodes", [])[:10]:
            print(f"- central: {node.get('path', node.get('id', ''))}")
        print(f"Archivos con alta conectividad: {len(summary.get('high_connectivity_files', []))}")
        for file_path in summary.get("high_connectivity_files", [])[:10]:
            print(f"- high-connectivity: {file_path}")
        if summary["warnings"]:
            print("Advertencias:")
            for warning in summary["warnings"]:
                print(f"- {warning}")
        return 0

    if args.command == "run-tasks":
        try:
            summary = run_pending_tasks(
                Path(args.path),
                max_tasks=args.max_tasks,
                output_dir=Path(args.output_dir),
                dry_run=args.dry_run,
                no_memory=args.no_memory,
                profile_override=args.profile,
                no_adaptive_limits=args.no_adaptive_limits,
                prompt_version=args.prompt_version,
                model_override=args.model if hasattr(args, "model") else None,
                use_benchmark_recommendations=args.use_benchmark_recommendations if hasattr(args, "use_benchmark_recommendations") else False,
            )
        except (OSError, ValueError) as error:
            print(f"Task run failed: {error}")
            return 1

        output_path = Path(args.output_dir) / "task_results.json"
        if summary.dry_run:
            print("Task dry-run completed.")
            print(f"Tasks requested: {summary.tasks_requested}")
            print(f"Tasks selected: {summary.tasks_selected}")
            for item in summary.dry_run_tasks:
                status = "ok" if item.valid_path and not item.errors else "error"
                truncated = " truncated" if item.truncated else ""
                print(f"- {item.task_id} {item.task_type} {item.file_path} [{status}{truncated}]")
                if item.prompt_preview:
                    print(f"  Prompt preview: {item.prompt_preview}")
                for error in item.errors:
                    print(f"  Error: {error}")
            print("Output: not written in dry-run mode")
            return 0

        print("Task run completed.")
        print(f"Model used: {summary.model_used or '(default)'}")
        print(f"Benchmark source: {summary.benchmark_source or 'none'}")
        print(f"Tasks requested: {summary.tasks_requested}")
        print(f"Tasks processed: {summary.tasks_processed}")
        print(f"Completed: {summary.tasks_completed}")
        print(f"Reused: {summary.tasks_reused}")
        print(f"Failed JSON: {summary.failed_json}")
        print(f"Failed model: {summary.failed_model}")
        print(f"Failed read: {summary.failed_read}")
        print(f"JSON repaired: {summary.json_repaired}")
        print(f"Output: {output_path.as_posix()}")
        return 0

    if args.command == "report":
        try:
            inputs = load_audit_inputs(
                Path(args.path),
                output_dir=Path(args.output_dir),
                results_path=Path(args.results) if args.results else None,
            )
        except FileNotFoundError as error:
            print(f"Report failed: {error}")
            return 1
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
                max_tasks=args.max_tasks if args.max_tasks is not None else args.max_files,
                max_files=args.max_files,
                use_memory=parse_bool(args.use_memory),
                use_graphify=parse_bool(args.use_graphify),
                read_only=parse_bool(args.read_only),
                output_dir=Path(args.output_dir),
            )
        except (OSError, ValueError) as error:
            response = {
                "status": "failed",
                "report_path": "",
                "summary": str(error),
                "warning": "Not applied automatically",
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
        if not args.report_path:
            response = {
                "mode": "suggest_patch",
                "status": "failed",
                "summary": "--report is required",
                "warning": "Not applied automatically",
                "patches_created": 0,
            }
            response["warning"] = "Not applied automatically"
            print(json.dumps(response, indent=2))
            return 1
        try:
            summary = suggest_patches(
                Path(args.path),
                report_path=Path(args.report_path),
                max_patches=args.max_patches,
                output_dir=Path(args.output_dir),
                dry_run=args.dry_run,
            )
        except (OSError, ValueError) as error:
            response = {
                "mode": "suggest_patch",
                "status": "failed",
                "summary": str(error),
                "warning": "Propuesta no aplicada automáticamente.",
                "patches_created": 0,
            }
            response["warning"] = "Not applied automatically"
            print(json.dumps(response, indent=2))
            return 1

        print(json.dumps(summary.to_dict(), indent=2))
        return 0

    if args.command == "model-stats":
        store = ModelProfileStore(DEFAULT_MEMORY_PATH)
        profiles = store.list_profiles(model=args.model, task_type=args.task_type)
        if args.recommendations:
            ollama_config = load_ollama_config()
            adaptive_config = load_adaptive_limits_config(
                fallback_default_max_chars=ollama_config.max_chars_per_file
            )
            rows = recommendations_for_profiles(profiles, config=adaptive_config)
        else:
            rows = [profile.to_dict() for profile in profiles]
        if args.json:
            print(json.dumps({"profiles": rows}, indent=2))
            return 0

        if not rows:
            print("No model profile stats found.")
            return 0

        print("Model profile stats:")
        for row in rows:
            print(
                " | ".join(
                    [
                        f"model={row['model']}",
                        f"task_type={row['task_type']}",
                        f"profile={row['profile']}",
                        f"prompt_version={row['prompt_version']}",
                        f"runs={row['runs_count']}",
                        f"success_rate={row['success_rate']:.2f}",
                        f"json_valid_rate={row['json_valid_rate']:.2f}",
                        f"json_repair_rate={row['json_repair_rate']:.2f}",
                        f"json_fail_rate={row['json_fail_rate']:.2f}",
                        f"average_response_ms={row['average_response_ms']:.1f}",
                        f"recommended_max_chars={row['recommended_max_chars']}",
                        f"recommended_prompt_version={row['recommended_prompt_version']}",
                    ]
                )
            )
            if args.recommendations:
                print(
                    "  "
                    + " | ".join(
                        [
                            f"effective_max_chars={row['effective_max_chars']}",
                            f"adaptive_reason={row['adaptive_reason']}",
                            f"adaptive_source={row['adaptive_source']}",
                        ]
                    )
                )
        return 0

    if args.command == "model-recommendations":
        rec = get_model_recommendations(
            task_type=args.task_type,
            profile=args.profile,
            latest_benchmark=args.latest_benchmark,
            include_demo_models=args.include_demo_models,
        )
        if args.json:
            print(json.dumps(rec.to_dict(), indent=2))
            return 0

        print("Model Recommendations")
        print(f"Recommended model: {rec.model}")
        print(f"Recommended prompt version: {rec.prompt_version}")
        print(f"Recommended max_chars: {rec.max_chars}")
        print(f"Best model for JSON: {rec.best_json_model or 'N/A'}")
        print(f"Fastest model: {rec.fastest_model or 'N/A'}")
        print(f"Most stable model: {rec.most_stable_model or 'N/A'}")
        print(f"Last benchmark: {rec.last_benchmark or 'N/A'}")
        print(f"Source: {rec.source}")
        print(f"Confidence: {rec.confidence}")
        if rec.suggestion:
            print(f"Suggestion: {rec.suggestion}")
        if rec.warnings:
            print("Warnings:")
            for w in rec.warnings:
                print(f"- {w}")
        return 0

    if args.command == "prompts":
        if args.prompts_command == "list":
            variants = [variant.to_dict() for variant in list_prompt_variants()]
            print(json.dumps({"prompts": variants}, indent=2))
            return 0

        if args.prompts_command == "recommend":
            store = ModelProfileStore(DEFAULT_MEMORY_PATH)
            selection = recommend_prompt(
                model=args.model,
                task_type=args.task_type,
                profile=args.profile,
                store=store,
            )
            data = selection.to_dict()
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print("Prompt recommendation:")
                print(f"model={args.model}")
                print(f"task_type={args.task_type}")
                print(f"profile={args.profile}")
                print(f"prompt_version={selection.version}")
                print(f"reason={selection.reason}")
                print(f"path={selection.path}")
            return 0

    if args.command == "benchmark-models":
        models = _resolve_benchmark_models(args)
        if not models:
            print("No models specified. Use --models or --all-ollama.")
            return 1

        if not args.dry_run:
            print("Local models can take several minutes. Wait until the command finishes.")
        report = run_benchmark(
            args.path,
            models=models,
            max_tasks=args.max_tasks,
            profile=args.profile,
            mode=args.mode,
            prompt_versions=args.prompt_versions,
            no_adaptive_limits=args.no_adaptive_limits,
            timeout_seconds=args.timeout_seconds,
            delay_between_models=args.delay_between_models,
            output_dir=Path(args.output_dir),
            dry_run=args.dry_run,
        )

        if args.dry_run:
            _print_benchmark_dry_run(report)
            return 0

        _print_benchmark_report(report)
        return 0 if not report.errors else 1

    if args.command == "benchmark-profile":
        models = _resolve_benchmark_models(args)
        if not models:
            print("No models specified. Use --models or --all-ollama.")
            return 1

        if not args.dry_run:
            print("Local models can take several minutes. Wait until the command finishes.")
        report = run_profile_benchmark(
            profiles=args.profile,
            models=models,
            max_tasks=args.max_tasks,
            prompt_versions=args.prompt_versions,
            no_adaptive_limits=args.no_adaptive_limits,
            timeout_seconds=args.timeout_seconds,
            delay_between_models=args.delay_between_models,
            output_dir=Path(args.output_dir),
            dry_run=args.dry_run,
        )

        if args.dry_run:
            _print_benchmark_dry_run(report)
            return 0

        _print_profile_benchmark_report(report)
        return 0 if not report.errors else 1

    if args.command == "calibrate-models":
        models = _resolve_benchmark_models(args)
        if not models:
            print("No models specified. Use --models or --all-ollama.")
            return 1

        if not args.dry_run:
            print("Local models can take several minutes. Wait until the command finishes.")
        report = run_profile_benchmark(
            profiles=args.profiles,
            models=models,
            max_tasks=args.max_tasks,
            timeout_seconds=args.timeout_seconds,
            delay_between_models=args.delay_between_models,
            output_dir=Path("reports/benchmarks"),
            dry_run=args.dry_run,
        )

        if args.dry_run:
            _print_benchmark_dry_run(report)
            return 0

        _print_profile_benchmark_report(report)
        return 0 if not report.errors else 1

    if args.command == "logs":
        if args.logs_command == "summary":
            summary = read_log_summary()
            print("Log summary:")
            print(f"  runs: {summary.get('runs', 0)} events")
            print(f"  tasks: {summary.get('tasks', 0)} events")
            print(f"  errors: {summary.get('errors', 0)} events")
            latest = summary.get("latest", {})
            if latest:
                print("  latest activity:")
                for cat, entry in latest.items():
                    line = json.dumps(entry, ensure_ascii=False, default=str)
                    print(f"    {cat}: {line[:120]}")
            return 0
        if args.logs_command == "errors":
            entries = read_log_errors(limit=args.limit)
            if not entries:
                print("No error logs found.")
                return 0
            print(f"Last {len(entries)} error(s):")
            for entry in entries:
                print(json.dumps(entry, ensure_ascii=False, default=str))
            return 0
        if args.logs_command == "tasks":
            entries = read_log_tasks(limit=args.limit)
            if not entries:
                print("No task logs found.")
                return 0
            print(f"Last {len(entries)} task(s):")
            for entry in entries:
                print(json.dumps(entry, ensure_ascii=False, default=str))
            return 0

    if args.command == "webui":
        from webui.server import run_webui
        run_webui(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0

    if args.command == "providers":
        from governor.providers import list_providers, all_providers_health, list_models_for_provider
        if args.providers_command == "list":
            providers = list_providers()
            print("Registered providers:")
            for p in providers:
                print(f"  - {p}")
            return 0
        if args.providers_command == "health":
            health = all_providers_health()
            for name, info in health.items():
                status = "OK" if info["available"] else f"unavailable: {info.get('error', 'unknown')}"
                print(f"  {name}: {status}")
            return 0
        if args.providers_command == "models":
            models = list_models_for_provider(args.provider)
            if not models:
                print(f"No models found for provider: {args.provider}")
            else:
                print(f"Models for {args.provider}:")
                for m in models:
                    print(f"  - {m}")
            return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def parse_bool(value: str) -> bool:
    return str(value).lower() == "true"


def print_audit_response(response: dict, *, dry_run: bool, output_dir: Path) -> None:
    if response.get("status") == "completed":
        print("Audit dry-run completed." if dry_run else "Audit completed.")
    else:
        print("Audit failed.")

    print(f"Project: {response.get('project_path', '')}")
    print(f"Adapter: {response.get('adapter', 'cli')}")
    print(f"Profile: {response.get('profile_detected', '')}")
    print(f"Tasks processed: {response.get('tasks_processed', 0)}")
    print(f"Reused from memory: {response.get('reused', 0)}")
    print(f"JSON valid: {response.get('json_valid', 0)}")
    print(f"JSON repaired: {response.get('json_repaired', 0)}")
    print(f"JSON failed: {response.get('json_failed', 0)}")
    if dry_run:
        print("Model calls: skipped")
        print("Final report: not generated in dry-run mode")
        print(f"Planned tasks: {(output_dir / 'tasks.json').as_posix()}")
    else:
        print(f"Markdown report: {response.get('report_markdown', '')}")
        print(f"JSON report: {response.get('report_json', '')}")
    if response.get("summary"):
        print(f"Summary: {response['summary']}")
    if response.get("errors"):
        print("Errors:")
        for error in response["errors"]:
            print(f"- {error}")
    print("Structured response:")
    print(json.dumps(response, indent=2))


def _resolve_benchmark_models(args: argparse.Namespace) -> list[str]:
    if args.all_ollama:
        try:
            return ollama_list_models()
        except (OSError, OllamaError):
            return []
    if args.models:
        return list(args.models)
    return []


def _print_benchmark_dry_run(report: object) -> None:
    if not isinstance(report, BenchmarkDryRun):
        print("Benchmark dry-run failed: unexpected report type.")
        return
    print("Benchmark dry-run")
    print(f"Project: {report.project_path}")
    print(f"Max tasks per model: {report.max_tasks}")
    print(f"Output dir: {report.output_dir}")
    if report.timeout_seconds is not None:
        print(f"Timeout per request: {report.timeout_seconds}s")
    print(f"Delay between models: {report.delay_between_models}s")
    if report.estimated_timeout_seconds is not None:
        print(f"Estimated worst-case timeout window: ~{report.estimated_timeout_seconds}s")
    print(f"Models to benchmark ({len(report.models)}):")
    for m in report.models:
        print(f"- {m}")
    print(f"Prompt versions ({len(report.prompt_versions)}):")
    for v in report.prompt_versions:
        print(f"- {v}")
    print(f"Tasks to use ({len(report.tasks)}):")
    for t in report.tasks:
        if "file_path" in t:
            print(f"- {t['file_path']} [{t.get('task_type', '')}]")
        elif "profile" in t:
            print(f"- profile={t['profile']} fixture={t.get('fixture', '')}")
        else:
            print(f"- {t}")
    print("Ollama calls: skipped (dry-run)")


def _print_benchmark_report(report: object) -> None:
    if not isinstance(report, BenchmarkReport):
        print("Benchmark failed: unexpected report type.")
        return
    print("Model Benchmark Report")
    if report.errors:
        print("Errors:")
        for error in report.errors:
            print(f"- {error}")
    if report.models:
        print("Models:")
        for model in report.models:
            print(
                f"- {model['model']}: "
                f"score={model['overall_score']:.4f} "
                f"json_valid_rate={model['json_valid_rate']:.2f} "
                f"success_rate={model['success_rate']:.2f} "
                f"avg_ms={model['average_response_ms']:.0f}"
            )
    else:
        print("No model results.")
    summary = report.summary
    print(f"Best overall: {summary.get('best_overall_model') or 'N/A'}")
    print(f"Best JSON: {summary.get('best_json_model') or 'N/A'}")
    print(f"Fastest: {summary.get('fastest_model') or 'N/A'}")
    print(f"Most stable: {summary.get('most_stable_model') or 'N/A'}")


def _print_profile_benchmark_report(report: object) -> None:
    if not isinstance(report, ProfileBenchmarkReport):
        print("Profile benchmark failed: unexpected report type.")
        return
    print("Profile Model Benchmark Report")
    if report.errors:
        print("Errors:")
        for error in report.errors:
            print(f"- {error}")
    for profile_name, data in report.profiles.items():
        print(f"\n--- {profile_name} ---")
        print(f"Best overall: {data.get('best_overall_model') or 'N/A'}")
        print(f"Best JSON: {data.get('best_json_model') or 'N/A'}")
        print(f"Fastest: {data.get('fastest_model') or 'N/A'}")
        print(f"Most stable: {data.get('most_stable_model') or 'N/A'}")
    summary = report.global_summary
    print(f"\nGlobal: best={summary.get('best_general_model') or 'N/A'}, most_consistent={summary.get('most_consistent_model') or 'N/A'}")


if __name__ == "__main__":
    raise SystemExit(main())
