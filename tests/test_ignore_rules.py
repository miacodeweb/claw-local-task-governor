from governor.scanner import is_relevant_file, should_ignore_file


def test_ignores_binary_and_minified_files(tmp_path):
    image = tmp_path / "logo.png"
    minified = tmp_path / "app.min.js"
    source = tmp_path / "app.js"

    assert should_ignore_file(image)
    assert should_ignore_file(minified)
    assert not should_ignore_file(source)


def test_marks_source_and_config_files_relevant(tmp_path):
    assert is_relevant_file(tmp_path / "src" / "main.py")
    assert is_relevant_file(tmp_path / "package.json")
    assert is_relevant_file(tmp_path / ".env.example")
    assert not is_relevant_file(tmp_path / "notes.txt")
