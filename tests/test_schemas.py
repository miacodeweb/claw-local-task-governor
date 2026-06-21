import copy
import json
from pathlib import Path

import pytest


SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


class ValidationError(AssertionError):
    pass


def load_schema(name):
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def validate(instance, schema, path="$"):
    schema_type = schema.get("type")
    if schema_type is not None:
        validate_type(instance, schema_type, path)

    if "enum" in schema and instance not in schema["enum"]:
        raise ValidationError(f"{path} must be one of {schema['enum']}")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise ValidationError(f"{path} missing required keys: {missing}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = [key for key in instance if key not in properties]
            if extra:
                raise ValidationError(f"{path} has extra keys: {extra}")

        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], f"{path}.{key}")

    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(f"{path} has too many items")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValidationError(f"{path} has too few items")
        if "items" in schema:
            for index, item in enumerate(instance):
                validate(item, schema["items"], f"{path}[{index}]")

    if isinstance(instance, str) and len(instance) < schema.get("minLength", 0):
        raise ValidationError(f"{path} is shorter than minLength")

    if isinstance(instance, int) and "minimum" in schema and instance < schema["minimum"]:
        raise ValidationError(f"{path} is lower than minimum")


def validate_type(instance, schema_type, path):
    allowed = schema_type if isinstance(schema_type, list) else [schema_type]
    if not any(matches_type(instance, item) for item in allowed):
        raise ValidationError(f"{path} type must be {allowed}")


def matches_type(instance, schema_type):
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
    raise AssertionError(f"unsupported test schema type: {schema_type}")


@pytest.fixture
def valid_file_analysis():
    return {
        "file": "src/main.py",
        "status": "needs_review",
        "risk": "medium",
        "summary": "One clear issue was found.",
        "findings": [
            {
                "line": 12,
                "type": "hardcoded_timeout",
                "severity": "medium",
                "evidence": "Timeout is fixed in code.",
                "recommendation": "Move the value to configuration.",
            }
        ],
        "needs_related_file": False,
        "related_files": [],
    }


def test_file_analysis_schema_accepts_valid_example(valid_file_analysis):
    validate(valid_file_analysis, load_schema("file_analysis.schema.json"))


def test_file_analysis_schema_rejects_bad_status(valid_file_analysis):
    invalid = copy.deepcopy(valid_file_analysis)
    invalid["status"] = "maybe"

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("file_analysis.schema.json"))


def test_file_analysis_schema_rejects_missing_finding_field(valid_file_analysis):
    invalid = copy.deepcopy(valid_file_analysis)
    del invalid["findings"][0]["recommendation"]

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("file_analysis.schema.json"))


def test_file_analysis_schema_rejects_extra_top_level_field(valid_file_analysis):
    invalid = copy.deepcopy(valid_file_analysis)
    invalid["markdown"] = "not allowed"

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("file_analysis.schema.json"))


def test_task_result_schema_accepts_valid_example(valid_file_analysis):
    valid = {
        "task_id": "task-0001",
        "project_path": "/demo",
        "file_path": "src/main.py",
        "file_hash": "abc123",
        "task_type": "inspect_code_file",
        "profile": "python",
        "status": "completed",
        "json_valid": True,
        "json_repaired": False,
        "risk": "medium",
        "result": valid_file_analysis,
        "created_at": "2026-06-21T00:00:00+00:00",
    }

    validate(valid, load_schema("task_result.schema.json"))


def test_task_result_schema_rejects_unknown_task_type(valid_file_analysis):
    invalid = {
        "task_id": "task-0001",
        "project_path": "/demo",
        "file_path": "src/main.py",
        "file_hash": "abc123",
        "task_type": "inspect_everything",
        "profile": "python",
        "status": "completed",
        "json_valid": True,
        "json_repaired": False,
        "risk": "medium",
        "result": valid_file_analysis,
        "created_at": "2026-06-21T00:00:00+00:00",
    }

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("task_result.schema.json"))


def test_task_result_schema_rejects_invalid_nested_result(valid_file_analysis):
    invalid_result = copy.deepcopy(valid_file_analysis)
    invalid_result["findings"][0]["severity"] = "optional"
    invalid = {
        "task_id": "task-0001",
        "project_path": "/demo",
        "file_path": "src/main.py",
        "file_hash": "abc123",
        "task_type": "inspect_code_file",
        "profile": "python",
        "status": "completed",
        "json_valid": True,
        "json_repaired": False,
        "risk": "medium",
        "result": invalid_result,
        "created_at": "2026-06-21T00:00:00+00:00",
    }

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("task_result.schema.json"))


def test_final_report_schema_accepts_valid_example():
    valid = {
        "status": "completed",
        "project_path": "/demo",
        "profile": "general",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "summary": "Audit completed with one finding.",
        "totals": {
            "tasks_total": 1,
            "tasks_completed": 1,
            "tasks_failed": 0,
            "findings_total": 1,
        },
        "findings": [
            {
                "file": "src/main.py",
                "line": None,
                "type": "example",
                "severity": "low",
                "evidence": "Example evidence.",
                "recommendation": "Review when implementing analysis.",
            }
        ],
        "files": [
            {
                "file": "src/main.py",
                "risk": "low",
                "status": "needs_review",
                "summary": "One low risk finding.",
            }
        ],
    }

    validate(valid, load_schema("final_report.schema.json"))


def test_final_report_schema_rejects_negative_totals():
    invalid = {
        "status": "completed",
        "project_path": "/demo",
        "profile": "general",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "summary": "Invalid totals.",
        "totals": {
            "tasks_total": -1,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "findings_total": 0,
        },
        "findings": [],
        "files": [],
    }

    with pytest.raises(ValidationError):
        validate(invalid, load_schema("final_report.schema.json"))
