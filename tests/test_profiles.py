from governor.profiles import load_all_profiles, load_profile


def test_loads_initial_profile_set():
    profiles = load_all_profiles()

    assert {
        "general",
        "php",
        "wordpress",
        "javascript",
        "python",
        "java",
        "docker",
        "config_files",
        "windows_folder",
        "linux_folder",
        "documentation",
    }.issubset(profiles)
    assert ".py" in profiles["python"].relevant_extensions
    assert "wp-config.php" in profiles["wordpress"].important_files
    assert "node_modules" in profiles["javascript"].ignore_dirs
    assert profiles["docker"].base_priority == "medium"
    assert profiles["docker"].recommended_prompt == "inspect_config_file.txt"
    assert profiles["config_files"].recommended_prompt == "inspect_config_file.txt"
    assert profiles["documentation"].recommended_prompt == "inspect_documentation_file.txt"


def test_missing_profile_falls_back_to_general():
    profile = load_profile("missing-profile")

    assert profile.name == "general"
    assert profile.recommended_prompt == "inspect_code_file.txt"
