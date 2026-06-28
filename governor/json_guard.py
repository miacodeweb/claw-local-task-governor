"""Basic JSON parsing, repair, and schema validation guard."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


@dataclass(frozen=True)
class JSONGuardResult:
    valid: bool
    repaired: bool
    data: Any
    errors: list[str]
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "repaired": self.repaired,
            "data": self.data,
            "errors": self.errors,
            "raw_text": self.raw_text,
        }


class JSONGuard:
    """Reusable JSON guard bound to an optional schema."""

    def __init__(self, schema: str | Path | dict | None = None) -> None:
        self.schema = schema

    def validate(self, raw_text: str) -> JSONGuardResult:
        return guard_json(raw_text, self.schema)


def guard_json(raw_text: str, schema: str | Path | dict | None = None) -> JSONGuardResult:
    """Parse imperfect JSON text and optionally validate it against a schema."""
    if raw_text is None or raw_text.strip() == "":
        return JSONGuardResult(
            valid=False,
            repaired=False,
            data=None,
            errors=["empty response"],
            raw_text=raw_text or "",
        )

    schema_data = load_schema(schema) if schema is not None else None
    candidates = build_json_candidates(raw_text)
    parse_errors: list[str] = []

    for candidate, repaired in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as error:
            parse_errors.append(f"json parse error at line {error.lineno}, column {error.colno}: {error.msg}")
            continue

        errors = validate_schema(data, schema_data) if schema_data is not None else []
        return JSONGuardResult(
            valid=not errors,
            repaired=repaired,
            data=data,
            errors=errors,
            raw_text=raw_text,
        )

    return JSONGuardResult(
        valid=False,
        repaired=False,
        data=None,
        errors=_final_parse_errors(raw_text, parse_errors),
        raw_text=raw_text,
    )


def parse_json(raw_text: str) -> JSONGuardResult:
    """Parse JSON without schema validation."""
    return guard_json(raw_text)


def load_schema(schema: str | Path | dict) -> dict:
    if isinstance(schema, dict):
        return schema

    schema_path = Path(schema)
    if not schema_path.is_absolute():
        schema_path = SCHEMAS_DIR / schema_path
    return json.loads(schema_path.read_text(encoding="utf-8"))


def build_json_candidates(raw_text: str) -> list[tuple[str, bool]]:
    """Return parse candidates with a flag indicating cleanup or repair."""
    candidates: list[tuple[str, bool]] = []
    seen: set[str] = set()

    def add(candidate: str, repaired: bool) -> None:
        normalized = candidate.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append((normalized, repaired))

    stripped = raw_text.strip()
    add(stripped, False)

    unfenced = strip_markdown_fence(stripped)
    add(unfenced, unfenced != stripped)

    for text, repaired in list(candidates):
        extracted = extract_json_text(text)
        if extracted is not None:
            add(extracted, repaired or extracted != text.strip())

    for text, repaired in list(candidates):
        without_trailing_commas = remove_trailing_commas(text)
        add(without_trailing_commas, repaired or without_trailing_commas != text)

    return candidates


def _final_parse_errors(raw_text: str, parse_errors: list[str]) -> list[str]:
    if "{" not in raw_text and "[" not in raw_text:
        return ["no JSON object or array found"]
    return parse_errors or ["no JSON object or array found"]


def strip_markdown_fence(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:json|JSON)?\s*(.*?)\s*```\s*", text, re.DOTALL)
    return match.group(1).strip() if match else text


def extract_json_text(text: str) -> str | None:
    """Extract the first balanced JSON object or array from mixed text."""
    start_positions = [index for index, char in enumerate(text) if char in "{["]
    for start in start_positions:
        extracted = _extract_balanced(text, start)
        if extracted is not None:
            return extracted
    return None


def remove_trailing_commas(text: str) -> str:
    """Remove simple trailing commas before object or array closers."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def validate_schema(instance: Any, schema: dict | None, path: str = "$") -> list[str]:
    """Validate the local schema subset used by this project."""
    if schema is None:
        return []

    errors: list[str] = []
    schema_type = schema.get("type")
    if schema_type is not None and not _matches_any_type(instance, schema_type):
        return [f"{path}: expected type {schema_type}"]

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value must be one of {schema['enum']}")

    if isinstance(instance, dict):
        errors.extend(_validate_object(instance, schema, path))
    elif isinstance(instance, list):
        errors.extend(_validate_array(instance, schema, path))
    elif isinstance(instance, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            errors.append(f"{path}: string is shorter than {min_length}")
    elif isinstance(instance, int) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: value is lower than {minimum}")

    return errors


def _validate_object(instance: dict, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for key in required:
        if key not in instance:
            errors.append(f"{path}.{key}: missing required field")

    if schema.get("additionalProperties") is False:
        for key in instance:
            if key not in properties:
                errors.append(f"{path}.{key}: unexpected field")

    for key, value in instance.items():
        if key in properties:
            errors.extend(validate_schema(value, properties[key], f"{path}.{key}"))

    return errors


def _validate_array(instance: list, schema: dict, path: str) -> list[str]:
    errors: list[str] = []

    min_items = schema.get("minItems")
    if min_items is not None and len(instance) < min_items:
        errors.append(f"{path}: array has fewer than {min_items} items")

    max_items = schema.get("maxItems")
    if max_items is not None and len(instance) > max_items:
        errors.append(f"{path}: array has more than {max_items} items")

    item_schema = schema.get("items")
    if item_schema is not None:
        for index, item in enumerate(instance):
            errors.extend(validate_schema(item, item_schema, f"{path}[{index}]"))

    return errors


def _matches_any_type(instance: Any, schema_type: str | list[str]) -> bool:
    allowed = schema_type if isinstance(schema_type, list) else [schema_type]
    return any(_matches_type(instance, item) for item in allowed)


def _matches_type(instance: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(instance, dict)
    if schema_type == "array":
        return isinstance(instance, list)
    if schema_type == "string":
        return isinstance(instance, str)
    if schema_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if schema_type == "boolean":
        return isinstance(instance, bool)
    if schema_type == "null":
        return instance is None
    return False


def _extract_balanced(text: str, start: int) -> str | None:
    opening = text[start]
    expected_closer = "}" if opening == "{" else "]"
    stack = [expected_closer]
    in_string = False
    escaped = False

    for index in range(start + 1, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return text[start : index + 1].strip()

    return None
