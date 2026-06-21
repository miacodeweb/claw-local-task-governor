from governor.profile_detector import detect_best_profile, detect_profiles


def test_detects_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    best = detect_best_profile(tmp_path)

    assert best.profile == "python"


def test_detects_wordpress_before_php(tmp_path):
    (tmp_path / "wp-config.php").write_text("<?php\n", encoding="utf-8")
    (tmp_path / "wp-content").mkdir()
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")

    profiles = detect_profiles(tmp_path)

    assert profiles[0].profile == "wordpress"
    assert any(profile.profile == "php" for profile in profiles)


def test_falls_back_to_general(tmp_path):
    best = detect_best_profile(tmp_path)

    assert best.profile == "general"


def test_detects_profile_rules_for_multiple_project_types(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_best_profile(tmp_path).profile == "javascript"

    (tmp_path / "package.json").unlink()
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    assert detect_best_profile(tmp_path).profile == "docker"
