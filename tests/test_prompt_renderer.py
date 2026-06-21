import pytest

from governor.prompt_renderer import PromptRenderError, render_prompt, render_repair_prompt


def test_render_code_prompt_includes_context_and_content():
    prompt = render_prompt(
        file_path="src/main.py",
        profile="python",
        task_type="inspect_code_file",
        file_content="print('hello')",
    )

    assert "src/main.py" in prompt
    assert "python" in prompt
    assert "inspect_code_file" in prompt
    assert "print('hello')" in prompt
    assert "Analyze a single file only." in prompt
    assert "Do not invent files" in prompt
    assert "Do not use markdown" in prompt
    assert "Return only valid JSON" in prompt
    assert "Maximum 5 findings" in prompt
    assert "{{" not in prompt


def test_render_config_prompt_is_generic_and_mentions_secret_handling():
    prompt = render_prompt(
        file_path="package.json",
        profile="javascript",
        task_type="inspect_config_file",
        file_content='{"scripts": {}}',
    )

    assert "configuration or project metadata file" in prompt
    assert "Do not reveal or repeat secret values" in prompt
    assert "package.json" in prompt
    assert "javascript" in prompt
    assert "WordPress" not in prompt


def test_render_prompt_rejects_unsupported_task_type():
    with pytest.raises(PromptRenderError):
        render_prompt(
            file_path="README.md",
            profile="general",
            task_type="inspect_documentation_file",
            file_content="# Demo",
        )


def test_render_repair_prompt_uses_invalid_response_as_content():
    prompt = render_repair_prompt(
        file_path="src/main.py",
        profile="python",
        task_type="inspect_code_file",
        invalid_response="```json\n{bad}\n```",
    )

    assert "Your previous response was not valid JSON" in prompt
    assert "Return only corrected valid JSON" in prompt
    assert "src/main.py" in prompt
    assert "```json\n{bad}\n```" in prompt
    assert "{{" not in prompt


def test_prompts_include_expected_file_analysis_schema():
    prompt = render_prompt(
        file_path="src/main.py",
        profile="general",
        task_type="inspect_code_file",
        file_content="pass",
    )

    for field in [
        '"file"',
        '"status"',
        '"risk"',
        '"summary"',
        '"findings"',
        '"needs_related_file"',
        '"related_files"',
    ]:
        assert field in prompt
