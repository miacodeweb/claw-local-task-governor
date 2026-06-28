from governor.profile_detector import detect_best_profile, detect_profiles


def test_detects_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    best = detect_best_profile(tmp_path)

    assert best.profile == "python"


def test_detects_general_project(tmp_path):
    (tmp_path / "notes.txt").write_text("plain notes\n", encoding="utf-8")

    best = detect_best_profile(tmp_path)

    assert best.profile == "general"


def test_detects_wordpress_before_php(tmp_path):
    (tmp_path / "wp-config.php").write_text("<?php\n", encoding="utf-8")
    (tmp_path / "wp-content").mkdir()
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")

    profiles = detect_profiles(tmp_path)

    assert profiles[0].profile == "wordpress"
    assert any(profile.profile == "php" for profile in profiles)


def test_detects_javascript_project(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    assert detect_best_profile(tmp_path).profile == "javascript"


def test_detects_java_project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")

    assert detect_best_profile(tmp_path).profile == "java"


def test_detects_docker_project(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    assert detect_best_profile(tmp_path).profile == "docker"


def test_forced_profile_overrides_detection(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    best = detect_best_profile(tmp_path, forced_profile="python")

    assert best.profile == "python"
    assert best.confidence == 1.0
    assert best.reason == "profile forced by user"


def test_fallback_safe_to_general(tmp_path):
    best = detect_best_profile(tmp_path)

    assert best.profile == "general"
