"""Release file validation tests for LocalScope 0.1.0."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class TestReleaseFiles:
    def test_changelog_exists(self):
        assert (ROOT / "CHANGELOG.md").is_file()
        content = _read("CHANGELOG.md")
        assert "0.1.0" in content

    def test_security_exists(self):
        assert (ROOT / "SECURITY.md").is_file()
        content = _read("SECURITY.md")
        assert "read-only" in content.lower()

    def test_contributing_exists(self):
        assert (ROOT / "CONTRIBUTING.md").is_file()

    def test_license_exists(self):
        assert (ROOT / "LICENSE").is_file()

    def test_bug_report_template_exists(self):
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").is_file()

    def test_feature_request_template_exists(self):
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").is_file()

    def test_issue_config_exists(self):
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").is_file()

    def test_pr_template_exists(self):
        assert (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file()

    def test_release_checklist_exists(self):
        assert (ROOT / "docs" / "RELEASE_CHECKLIST.md").is_file()
        content = _read("docs/RELEASE_CHECKLIST.md")
        assert "git tag" in content

    def test_gitignore_has_key_exclusions(self):
        content = _read(".gitignore")
        for pattern in ["logs/", "reports/", "data/", ".env", ".sqlite"]:
            assert pattern in content, f".gitignore missing: {pattern}"

    def test_gitignore_excludes_node_modules(self):
        content = _read(".gitignore")
        assert "node_modules/" in content

    def test_pyproject_has_localscope_name(self):
        content = _read("pyproject.toml")
        assert 'name = "localscope"' in content

    def test_pyproject_has_version(self):
        content = _read("pyproject.toml")
        assert 'version = "0.1.0rc1"' in content

    def test_no_dangerous_commands_in_main(self):
        from governor.safety import FORBIDDEN_TOOL_NAMES
        assert "apply_patch" in FORBIDDEN_TOOL_NAMES
        assert "write_file" in FORBIDDEN_TOOL_NAMES
        assert "run_command" in FORBIDDEN_TOOL_NAMES

    def test_config_example_not_leaked(self):
        content = _read(".gitignore")
        assert "config.example.yaml" not in content or "!config.example.yaml" in content

    def test_release_mvp_docs_exist(self):
        assert (ROOT / "docs" / "RELEASE_MVP.md").is_file()

    def test_readme_exists(self):
        assert (ROOT / "README.md").is_file()
        content = _read("README.md")
        assert "LocalScope" in content
