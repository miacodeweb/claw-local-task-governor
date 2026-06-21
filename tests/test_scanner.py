import json

from governor.scanner import scan_project


def test_scan_project_writes_report_and_hashes_relevant_files(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "logo.png").write_bytes(b"not really an image")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "ignored.js").write_text("console.log('skip')\n", encoding="utf-8")
    output_dir = tmp_path / "reports"

    result = scan_project(project, output_dir=output_dir)

    assert result.profile_detected == "python"
    assert result.files_found == 2
    assert result.files_ignored == 2
    assert result.relevant_files == 2

    report = json.loads((output_dir / "scan_result.json").read_text(encoding="utf-8"))
    files = {item["path"]: item for item in report["files"]}
    assert files["main.py"]["sha256"]
    assert files["main.py"]["modified_at"]
    assert files["pyproject.toml"]["importance"] == "high"
    assert "node_modules" in {item["path"] for item in report["ignored"]}


def test_scan_marks_secret_like_file_without_reading_content_into_report(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("TOKEN=super-secret\n", encoding="utf-8")

    result = scan_project(project, output_dir=tmp_path / "reports")

    env_file = next(file for file in result.files if file.path == ".env")
    assert env_file.secret_like is True
    assert env_file.sha256

    report_text = (tmp_path / "reports" / "scan_result.json").read_text(encoding="utf-8")
    assert "super-secret" not in report_text


def test_scan_ignores_governor_output_files_when_inside_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    output_dir = project / "reports"

    scan_project(project, output_dir=output_dir)
    (output_dir / "tasks.json").write_text("{}", encoding="utf-8")
    (output_dir / "task_results.json").write_text("{}", encoding="utf-8")
    result = scan_project(project, output_dir=output_dir)

    assert all(file.path != "reports/scan_result.json" for file in result.files)
    assert all(file.path != "reports/tasks.json" for file in result.files)
    assert all(file.path != "reports/task_results.json" for file in result.files)
    assert any(item.path == "reports/scan_result.json" for item in result.ignored)
    assert any(item.path == "reports/tasks.json" for item in result.ignored)
    assert any(item.path == "reports/task_results.json" for item in result.ignored)


def test_scan_applies_profile_specific_relevant_extensions(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "composer.json").write_text("{}", encoding="utf-8")
    (project / "template.phtml").write_text("<h1>Hello</h1>", encoding="utf-8")

    result = scan_project(project, output_dir=tmp_path / "reports")

    files = {item.path: item for item in result.files}
    assert result.profile_detected == "php"
    assert files["template.phtml"].relevant is True
    assert files["template.phtml"].sha256
