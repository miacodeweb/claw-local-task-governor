from governor.profiles import load_all_profiles, load_profile


def test_loads_initial_profile_set():
    profiles = load_all_profiles()

    assert {"general", "php", "wordpress", "javascript", "python", "java", "docker"}.issubset(profiles)
    assert ".py" in profiles["python"].relevant_extensions
    assert "wp-config.php" in profiles["wordpress"].important_files
    assert "node_modules" in profiles["javascript"].ignore_dirs


def test_missing_profile_falls_back_to_general():
    profile = load_profile("missing-profile")

    assert profile.name == "general"
    assert profile.recommended_prompt == "inspect_code_file.txt"
