"""Prompt template loading and rendering for file-level microtasks."""

from __future__ import annotations

import re
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

TASK_PROMPT_FILES = {
    "inspect_code_file": "inspect_code_file.txt",
    "inspect_config_file": "inspect_config_file.txt",
}


class PromptRenderError(ValueError):
    """Raised when a prompt template cannot be rendered safely."""


def render_prompt(
    *,
    file_path: str,
    profile: str,
    task_type: str,
    file_content: str,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> str:
    """Render the prompt template for a supported file inspection task."""
    template_name = TASK_PROMPT_FILES.get(task_type)
    if template_name is None:
        raise PromptRenderError(f"unsupported task type for prompt rendering: {task_type}")

    template = load_prompt_template(template_name, prompts_dir=prompts_dir)
    return render_template(
        template,
        {
            "file_path": file_path,
            "profile": profile,
            "task_type": task_type,
            "file_content": file_content,
        },
    )


def render_repair_prompt(
    *,
    file_path: str,
    profile: str,
    task_type: str,
    invalid_response: str,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> str:
    """Render the JSON repair prompt for a failed file analysis response."""
    template = load_prompt_template("repair_json.txt", prompts_dir=prompts_dir)
    return render_template(
        template,
        {
            "file_path": file_path,
            "profile": profile,
            "task_type": task_type,
            "file_content": invalid_response,
        },
    )


def load_prompt_template(template_name: str, prompts_dir: Path | str = PROMPTS_DIR) -> str:
    prompt_path = Path(prompts_dir) / template_name
    return prompt_path.read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)

    if re.search(r"{{[a-zA-Z_][a-zA-Z0-9_]*}}", rendered):
        raise PromptRenderError("prompt template contains unresolved placeholders")

    return rendered
