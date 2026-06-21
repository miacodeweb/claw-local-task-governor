import json

from governor.json_guard import guard_json, parse_json


VALID_FILE_ANALYSIS = {
    "file": "src/main.py",
    "status": "ok",
    "risk": "none",
    "summary": "No clear issues found.",
    "findings": [],
    "needs_related_file": False,
    "related_files": [],
}


def test_parse_json_accepts_valid_json():
    result = parse_json('{"ok": true}')

    assert result.valid is True
    assert result.repaired is False
    assert result.data == {"ok": True}
    assert result.errors == []


def test_guard_json_validates_file_analysis_schema():
    result = guard_json(
        """
        {
          "file": "src/main.py",
          "status": "ok",
          "risk": "none",
          "summary": "No clear issues found.",
          "findings": [],
          "needs_related_file": false,
          "related_files": []
        }
        """,
        "file_analysis.schema.json",
    )

    assert result.valid is True
    assert result.data["file"] == "src/main.py"


def test_guard_json_extracts_json_from_surrounding_text():
    result = guard_json(
        'Here is the result: {"file":"src/main.py","status":"ok","risk":"none",'
        '"summary":"Clean","findings":[],"needs_related_file":false,"related_files":[]} done.',
        "file_analysis.schema.json",
    )

    assert result.valid is True
    assert result.repaired is True
    assert result.data["status"] == "ok"


def test_guard_json_strips_markdown_json_fence():
    result = guard_json(
        """```json
        {
          "file": "src/main.py",
          "status": "ok",
          "risk": "none",
          "summary": "No clear issues found.",
          "findings": [],
          "needs_related_file": false,
          "related_files": []
        }
        ```""",
        "file_analysis.schema.json",
    )

    assert result.valid is True
    assert result.repaired is True


def test_guard_json_repairs_simple_trailing_commas():
    result = guard_json(
        """
        {
          "file": "src/main.py",
          "status": "ok",
          "risk": "none",
          "summary": "No clear issues found.",
          "findings": [],
          "needs_related_file": false,
          "related_files": [],
        }
        """,
        "file_analysis.schema.json",
    )

    assert result.valid is True
    assert result.repaired is True


def test_guard_json_reports_empty_response():
    result = guard_json("", "file_analysis.schema.json")

    assert result.valid is False
    assert result.data is None
    assert result.errors == ["empty response"]


def test_guard_json_reports_missing_fields():
    result = guard_json(
        '{"file":"src/main.py","status":"ok","risk":"none"}',
        "file_analysis.schema.json",
    )

    assert result.valid is False
    assert any("summary" in error for error in result.errors)
    assert any("findings" in error for error in result.errors)


def test_guard_json_reports_enum_errors():
    invalid = dict(VALID_FILE_ANALYSIS)
    invalid["risk"] = "maybe"

    result = guard_json(json.dumps(invalid), "file_analysis.schema.json")

    assert result.valid is False
    assert any("risk" in error and "one of" in error for error in result.errors)


def test_guard_json_reports_extra_fields():
    invalid = dict(VALID_FILE_ANALYSIS)
    invalid["markdown"] = "not allowed"

    result = guard_json(json.dumps(invalid), "file_analysis.schema.json")

    assert result.valid is False
    assert any("markdown" in error and "unexpected" in error for error in result.errors)


def test_guard_json_reports_unparseable_text():
    result = guard_json("not json at all", "file_analysis.schema.json")

    assert result.valid is False
    assert result.data is None
    assert result.errors
