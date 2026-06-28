from pathlib import Path

from governor.scanner import scan_project
from governor.profile_detector import detect_best_profile

CALIBRATION_DIR = Path(__file__).resolve().parent / "fixtures" / "calibration_projects"

PROJECTS = [
    "python_project",
    "javascript_project",
    "java_project",
    "php_project",
    "wordpress_project",
    "docker_project",
    "config_files_project",
    "windows_folder",
    "linux_folder",
]

EXPECTED_PROFILES = {
    "python_project": "python",
    "javascript_project": "javascript",
    "java_project": "java",
    "php_project": "php",
    "wordpress_project": "wordpress",
    "docker_project": "docker",
    "config_files_project": "config_files",
    "windows_folder": "general",
    "linux_folder": "general",
}

MAX_FILE_SIZE = 4096

DANGER_PATTERNS = [b"BEGIN RSA PRIVATE KEY", b"ghp_", b"sk-", b"Bearer", b"token:"]
SECRET_NAMES = {".env", ".env.production", "credentials.json", "id_rsa"}


def _project_path(name):
    return CALIBRATION_DIR / name


class TestCalibrationFixtures:
    def test_all_fixtures_exist(self):
        for name in PROJECTS:
            path = _project_path(name)
            assert path.is_dir(), f"{name} directory missing"

    def test_each_fixture_has_files(self):
        for name in PROJECTS:
            path = _project_path(name)
            files = [f for f in path.rglob("*") if f.is_file()]
            assert 3 <= len(files) <= 10, f"{name} has {len(files)} files, expected 3-10"

    def test_no_fixture_files_are_too_large(self):
        for name in PROJECTS:
            path = _project_path(name)
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    size = file_path.stat().st_size
                    assert size <= MAX_FILE_SIZE, f"{file_path} is {size} bytes, max {MAX_FILE_SIZE}"

    def test_no_real_secrets(self):
        secrets = {"replace_with_real_password", "replace_with_real_key"}
        for name in PROJECTS:
            path = _project_path(name)
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    content = file_path.read_text(encoding="utf-8")
                    assert "password_here" not in content or file_path.name in {"wp-config-sample.php", "wp-config.php"}, \
                        f"{file_path} contains placeholder secret"
                    for secret in secrets:
                        assert secret not in content, f"{file_path} contains placeholder: {secret}"

    def test_no_secret_filenames(self):
        for name in PROJECTS:
            path = _project_path(name)
            for file_path in path.rglob("*"):
                assert file_path.name not in SECRET_NAMES, f"{file_path} is a secret filename"

    def test_no_dangerous_content_in_fixtures(self):
        for name in PROJECTS:
            path = _project_path(name)
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    try:
                        content = file_path.read_bytes()
                    except OSError:
                        continue
                    for pattern in DANGER_PATTERNS:
                        assert pattern not in content, \
                            f"{file_path} contains sensitive pattern: {pattern.decode()}"

    def test_scanner_can_process_each_fixture(self, tmp_path):
        for name in PROJECTS:
            src = _project_path(name)
            output = tmp_path / name / "reports"
            result = scan_project(src, output_dir=output)
            assert result.files_found >= 2, f"{name}: expected 2+ files, got {result.files_found}"

    def test_profile_detection_matches_expected(self):
        for name, expected in EXPECTED_PROFILES.items():
            path = _project_path(name)
            signal = detect_best_profile(path)
            assert signal.profile == expected, \
                f"{name}: expected {expected}, got {signal.profile} (confidence={signal.confidence:.2f}, reason={signal.reason})"
