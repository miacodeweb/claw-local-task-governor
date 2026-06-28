from pathlib import Path

import pytest

from governor.safety import (
    FORBIDDEN_TOOL_NAMES,
    MAX_TASKS_LIMIT,
    normalize_path_text,
    validate_max_tasks,
    validate_mcp_tool_names,
    validate_project_path,
    validate_read_only,
    validate_report_path,
)


def test_normalize_path_text_strips_wrapping_quotes_and_spaces():
    assert normalize_path_text('  "D:/My Project"  ') == "D:/My Project"
    assert normalize_path_text("  'D:/My Project'  ") == "D:/My Project"


def test_validate_project_path_accepts_existing_directory_with_spaces(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()

    assert validate_project_path(f'"{project}"') == project.resolve()


def test_validate_project_path_rejects_empty_missing_and_filesystem_root(tmp_path):
    with pytest.raises(ValueError, match="path is required"):
        validate_project_path("")

    with pytest.raises(ValueError, match="does not exist"):
        validate_project_path(tmp_path / "missing")

    root = Path(tmp_path.anchor or "/")
    with pytest.raises(ValueError, match="filesystem root"):
        validate_project_path(root)


def test_validate_max_tasks_bounds():
    assert validate_max_tasks("5") == 5

    with pytest.raises(ValueError, match="greater than 0"):
        validate_max_tasks(-1)
    with pytest.raises(ValueError, match=f"less than or equal to {MAX_TASKS_LIMIT}"):
        validate_max_tasks(MAX_TASKS_LIMIT + 1)


def test_validate_read_only_rejects_false():
    validate_read_only(True)

    with pytest.raises(ValueError, match="read_only=false rejected"):
        validate_read_only(False)


def test_validate_report_path_restricts_to_audit_reports_under_reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    audit = reports / "audit-20260623-120000.json"
    audit.write_text("{}", encoding="utf-8")
    other = tmp_path / "audit-outside.json"
    other.write_text("{}", encoding="utf-8")
    not_audit = reports / "notes.json"
    not_audit.write_text("{}", encoding="utf-8")

    assert validate_report_path(audit, reports_root=reports) == audit.resolve()

    with pytest.raises(ValueError, match="must be inside"):
        validate_report_path(other, reports_root=reports)
    with pytest.raises(ValueError, match="audit-"):
        validate_report_path(not_audit, reports_root=reports)


def test_validate_mcp_tool_names_rejects_forbidden_or_unexpected():
    validate_mcp_tool_names(
        {"localscope_audit", "localscope_status", "localscope_report", "localscope_graph_info"}
    )

    with pytest.raises(ValueError, match="forbidden"):
        validate_mcp_tool_names({"localscope_audit", "shell"})
    with pytest.raises(ValueError, match="unexpected"):
        validate_mcp_tool_names({"localscope_audit", "custom_tool"})

    assert {"shell", "exec"}.issubset(FORBIDDEN_TOOL_NAMES)
