"""Operational model profile metrics for LocalScope.

This module tracks model behavior observed during local task runs. It stores
operational counters only; it does not train, fine-tune, or modify models.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROVIDER = "ollama"
DEFAULT_PROFILE = "general"
DEFAULT_PROMPT_VERSION = "v1"
DEFAULT_RECOMMENDED_MAX_CHARS = 12000
MIN_RECOMMENDED_MAX_CHARS = 2000
MAX_RECOMMENDED_MAX_CHARS = 24000
SUCCESS_GROWTH_CHARS = 500

ADVANCED_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "model": "TEXT NOT NULL",
    "provider": "TEXT NOT NULL DEFAULT 'ollama'",
    "task_type": "TEXT NOT NULL",
    "profile": "TEXT NOT NULL DEFAULT 'general'",
    "prompt_version": "TEXT NOT NULL DEFAULT 'v1'",
    "runs_count": "INTEGER DEFAULT 0",
    "success_count": "INTEGER DEFAULT 0",
    "json_valid_count": "INTEGER DEFAULT 0",
    "json_repaired_count": "INTEGER DEFAULT 0",
    "json_failed_count": "INTEGER DEFAULT 0",
    "model_failed_count": "INTEGER DEFAULT 0",
    "read_failed_count": "INTEGER DEFAULT 0",
    "truncated_count": "INTEGER DEFAULT 0",
    "average_response_ms": "REAL DEFAULT 0",
    "average_input_chars": "REAL DEFAULT 0",
    "average_output_chars": "REAL DEFAULT 0",
    "recommended_max_chars": f"INTEGER DEFAULT {DEFAULT_RECOMMENDED_MAX_CHARS}",
    "recommended_prompt_version": "TEXT DEFAULT 'v1'",
    "last_error": "TEXT DEFAULT ''",
    "last_seen_at": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    # Compatibility columns used by the first memory implementation.
    "json_fail_count": "INTEGER DEFAULT 0",
    "json_repair_count": "INTEGER DEFAULT 0",
    "average_response_time": "REAL DEFAULT 0",
}


@dataclass(frozen=True)
class ModelProfileEvent:
    model: str
    task_type: str
    profile: str = DEFAULT_PROFILE
    prompt_version: str = DEFAULT_PROMPT_VERSION
    provider: str = DEFAULT_PROVIDER
    status: str = "completed"
    json_valid: bool = False
    json_repaired: bool = False
    truncated: bool = False
    response_time_ms: float | None = None
    input_chars: int = 0
    output_chars: int = 0
    current_max_chars: int | None = None
    error: str = ""


@dataclass(frozen=True)
class ModelProfileStats:
    model: str
    provider: str
    task_type: str
    profile: str
    prompt_version: str
    runs_count: int
    success_count: int
    json_valid_count: int
    json_repaired_count: int
    json_failed_count: int
    model_failed_count: int
    read_failed_count: int
    truncated_count: int
    average_response_ms: float
    average_input_chars: float
    average_output_chars: float
    recommended_max_chars: int
    recommended_prompt_version: str
    last_error: str
    last_seen_at: str
    created_at: str
    updated_at: str

    @property
    def json_fail_count(self) -> int:
        return self.json_failed_count

    @property
    def json_repair_count(self) -> int:
        return self.json_repaired_count

    @property
    def average_response_time(self) -> float:
        return self.average_response_ms / 1000

    @property
    def success_rate(self) -> float:
        return _rate(self.success_count, self.runs_count)

    @property
    def json_valid_rate(self) -> float:
        return _rate(self.json_valid_count, self.runs_count)

    @property
    def json_repair_rate(self) -> float:
        return _rate(self.json_repaired_count, self.runs_count)

    @property
    def json_fail_rate(self) -> float:
        return _rate(self.json_failed_count, self.runs_count)

    @property
    def model_fail_rate(self) -> float:
        return _rate(self.model_failed_count, self.runs_count)

    @property
    def truncation_rate(self) -> float:
        return _rate(self.truncated_count, self.runs_count)

    def rates(self) -> dict[str, float]:
        return {
            "success_rate": self.success_rate,
            "json_valid_rate": self.json_valid_rate,
            "json_repair_rate": self.json_repair_rate,
            "json_fail_rate": self.json_fail_rate,
            "model_fail_rate": self.model_fail_rate,
            "truncation_rate": self.truncation_rate,
        }

    def to_dict(self) -> dict[str, Any]:
        data = {
            "model": self.model,
            "provider": self.provider,
            "task_type": self.task_type,
            "profile": self.profile,
            "prompt_version": self.prompt_version,
            "runs_count": self.runs_count,
            "success_count": self.success_count,
            "json_valid_count": self.json_valid_count,
            "json_repaired_count": self.json_repaired_count,
            "json_failed_count": self.json_failed_count,
            "model_failed_count": self.model_failed_count,
            "read_failed_count": self.read_failed_count,
            "truncated_count": self.truncated_count,
            "average_response_ms": self.average_response_ms,
            "average_input_chars": self.average_input_chars,
            "average_output_chars": self.average_output_chars,
            "recommended_max_chars": self.recommended_max_chars,
            "recommended_prompt_version": self.recommended_prompt_version,
            "last_error": self.last_error,
            "last_seen_at": self.last_seen_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # Compatibility aliases.
            "json_fail_count": self.json_fail_count,
            "json_repair_count": self.json_repair_count,
            "average_response_time": self.average_response_time,
        }
        data.update(self.rates())
        return data


class ModelProfileStore:
    """SQLite store for operational model metrics."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            self._ensure_schema(connection)

    def record_task_result(self, event: ModelProfileEvent) -> ModelProfileStats:
        with self._connect() as connection:
            self._ensure_schema(connection)
            return self.record_task_result_with_connection(connection, event)

    def record_task_result_with_connection(
        self,
        connection: sqlite3.Connection,
        event: ModelProfileEvent,
    ) -> ModelProfileStats:
        self._ensure_schema(connection)
        normalized = _normalize_event(event)
        now = _utc_now()
        row = connection.execute(
            """
            SELECT *
            FROM model_profiles
            WHERE model = ?
              AND provider = ?
              AND task_type = ?
              AND profile = ?
              AND prompt_version = ?
            """,
            (
                normalized.model,
                normalized.provider,
                normalized.task_type,
                normalized.profile,
                normalized.prompt_version,
            ),
        ).fetchone()

        if row is None:
            created_at = now
            previous_runs = 0
            runs_count = 1
            success_count = 1 if _is_success(normalized) else 0
            json_valid_count = 1 if normalized.json_valid else 0
            json_repaired_count = 1 if normalized.json_repaired else 0
            json_failed_count = 1 if _is_json_failure(normalized) else 0
            model_failed_count = 1 if normalized.status == "failed_model" else 0
            read_failed_count = 1 if normalized.status == "failed_read" else 0
            truncated_count = 1 if normalized.truncated else 0
            average_response_ms = _average(0, previous_runs, normalized.response_time_ms)
            average_input_chars = _average(0, previous_runs, normalized.input_chars)
            average_output_chars = _average(0, previous_runs, normalized.output_chars)
            recommended_max_chars = _adapt_recommended_max_chars(
                current_max_chars=int(normalized.current_max_chars or DEFAULT_RECOMMENDED_MAX_CHARS),
                json_valid=normalized.json_valid,
                json_repaired=normalized.json_repaired,
            )
            connection.execute(
                """
                INSERT INTO model_profiles (
                    model,
                    provider,
                    task_type,
                    profile,
                    prompt_version,
                    runs_count,
                    success_count,
                    json_valid_count,
                    json_repaired_count,
                    json_failed_count,
                    model_failed_count,
                    read_failed_count,
                    truncated_count,
                    average_response_ms,
                    average_input_chars,
                    average_output_chars,
                    recommended_max_chars,
                    recommended_prompt_version,
                    last_error,
                    last_seen_at,
                    created_at,
                    updated_at,
                    json_fail_count,
                    json_repair_count,
                    average_response_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.model,
                    normalized.provider,
                    normalized.task_type,
                    normalized.profile,
                    normalized.prompt_version,
                    runs_count,
                    success_count,
                    json_valid_count,
                    json_repaired_count,
                    json_failed_count,
                    model_failed_count,
                    read_failed_count,
                    truncated_count,
                    average_response_ms,
                    average_input_chars,
                    average_output_chars,
                    recommended_max_chars,
                    normalized.prompt_version,
                    normalized.error,
                    now,
                    created_at,
                    now,
                    json_failed_count,
                    json_repaired_count,
                    average_response_ms / 1000,
                ),
            )
        else:
            previous_runs = int(row["runs_count"] or 0)
            runs_count = previous_runs + 1
            success_count = int(row["success_count"] or 0) + (1 if _is_success(normalized) else 0)
            json_valid_count = int(row["json_valid_count"] or 0) + (1 if normalized.json_valid else 0)
            json_repaired_count = int(row["json_repaired_count"] or 0) + (1 if normalized.json_repaired else 0)
            json_failed_count = int(row["json_failed_count"] or 0) + (1 if _is_json_failure(normalized) else 0)
            model_failed_count = int(row["model_failed_count"] or 0) + (
                1 if normalized.status == "failed_model" else 0
            )
            read_failed_count = int(row["read_failed_count"] or 0) + (
                1 if normalized.status == "failed_read" else 0
            )
            truncated_count = int(row["truncated_count"] or 0) + (1 if normalized.truncated else 0)
            average_response_ms = _average(
                float(row["average_response_ms"] or 0),
                previous_runs,
                normalized.response_time_ms,
            )
            average_input_chars = _average(
                float(row["average_input_chars"] or 0),
                previous_runs,
                normalized.input_chars,
            )
            average_output_chars = _average(
                float(row["average_output_chars"] or 0),
                previous_runs,
                normalized.output_chars,
            )
            recommended_max_chars = _adapt_recommended_max_chars(
                current_max_chars=int(normalized.current_max_chars or row["recommended_max_chars"] or DEFAULT_RECOMMENDED_MAX_CHARS),
                json_valid=normalized.json_valid,
                json_repaired=normalized.json_repaired,
            )
            connection.execute(
                """
                UPDATE model_profiles
                SET runs_count = ?,
                    success_count = ?,
                    json_valid_count = ?,
                    json_repaired_count = ?,
                    json_failed_count = ?,
                    model_failed_count = ?,
                    read_failed_count = ?,
                    truncated_count = ?,
                    average_response_ms = ?,
                    average_input_chars = ?,
                    average_output_chars = ?,
                    recommended_max_chars = ?,
                    recommended_prompt_version = ?,
                    last_error = ?,
                    last_seen_at = ?,
                    updated_at = ?,
                    json_fail_count = ?,
                    json_repair_count = ?,
                    average_response_time = ?
                WHERE id = ?
                """,
                (
                    runs_count,
                    success_count,
                    json_valid_count,
                    json_repaired_count,
                    json_failed_count,
                    model_failed_count,
                    read_failed_count,
                    truncated_count,
                    average_response_ms,
                    average_input_chars,
                    average_output_chars,
                    recommended_max_chars,
                    str(row["recommended_prompt_version"] or normalized.prompt_version),
                    normalized.error or str(row["last_error"] or ""),
                    now,
                    now,
                    json_failed_count,
                    json_repaired_count,
                    average_response_ms / 1000,
                    row["id"],
                ),
            )

        recommended_prompt_version = self.recommend_prompt_version_with_connection(
            connection,
            model=normalized.model,
            task_type=normalized.task_type,
            profile=normalized.profile,
            provider=normalized.provider,
        )
        connection.execute(
            """
            UPDATE model_profiles
            SET recommended_prompt_version = ?
            WHERE model = ?
              AND provider = ?
              AND task_type = ?
              AND profile = ?
            """,
            (
                recommended_prompt_version,
                normalized.model,
                normalized.provider,
                normalized.task_type,
                normalized.profile,
            ),
        )

        stored = self.get_profile_with_connection(
            connection,
            model=normalized.model,
            task_type=normalized.task_type,
            profile=normalized.profile,
            prompt_version=normalized.prompt_version,
            provider=normalized.provider,
        )
        if stored is None:
            raise RuntimeError("model profile was not saved")
        return stored

    def get_profile(
        self,
        *,
        model: str,
        task_type: str,
        profile: str = DEFAULT_PROFILE,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        provider: str = DEFAULT_PROVIDER,
    ) -> ModelProfileStats | None:
        with self._connect() as connection:
            self._ensure_schema(connection)
            return self.get_profile_with_connection(
                connection,
                model=model,
                task_type=task_type,
                profile=profile,
                prompt_version=_normalize_prompt_version(prompt_version),
                provider=provider,
            )

    def get_profile_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        model: str,
        task_type: str,
        profile: str = DEFAULT_PROFILE,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        provider: str = DEFAULT_PROVIDER,
    ) -> ModelProfileStats | None:
        self._ensure_schema(connection)
        prompt_version = _normalize_prompt_version(prompt_version)
        row = connection.execute(
            """
            SELECT *
            FROM model_profiles
            WHERE model = ?
              AND provider = ?
              AND task_type = ?
              AND profile = ?
              AND prompt_version = ?
            """,
            (model, provider, task_type, profile, prompt_version),
        ).fetchone()
        return profile_from_row(row) if row is not None else None

    def list_profiles(
        self,
        *,
        model: str | None = None,
        task_type: str | None = None,
    ) -> list[ModelProfileStats]:
        clauses: list[str] = []
        params: list[str] = []
        if model:
            clauses.append("model = ?")
            params.append(model)
        if task_type:
            clauses.append("task_type = ?")
            params.append(task_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                f"""
                SELECT *
                FROM model_profiles
                {where}
                ORDER BY model, task_type, profile, prompt_version
                """,
                tuple(params),
            ).fetchall()
        return [profile_from_row(row) for row in rows]

    def recommend_prompt_version(
        self,
        *,
        model: str,
        task_type: str,
        profile: str = DEFAULT_PROFILE,
        provider: str = DEFAULT_PROVIDER,
        available_versions: set[str] | None = None,
    ) -> str:
        with self._connect() as connection:
            self._ensure_schema(connection)
            return self.recommend_prompt_version_with_connection(
                connection,
                model=model,
                task_type=task_type,
                profile=profile,
                provider=provider,
                available_versions=available_versions,
            )

    def recommend_prompt_version_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        model: str,
        task_type: str,
        profile: str = DEFAULT_PROFILE,
        provider: str = DEFAULT_PROVIDER,
        available_versions: set[str] | None = None,
    ) -> str:
        self._ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT *
            FROM model_profiles
            WHERE model = ?
              AND provider = ?
              AND task_type = ?
              AND profile = ?
            """,
            (model, provider, task_type, profile),
        ).fetchall()
        candidates = [profile_from_row(row) for row in rows]
        if available_versions is not None:
            candidates = [item for item in candidates if item.prompt_version in available_versions]
        if not candidates:
            return DEFAULT_PROMPT_VERSION

        best = max(
            candidates,
            key=lambda item: (
                item.json_valid_rate,
                item.success_rate,
                -item.json_fail_rate,
                -item.model_fail_rate,
                item.runs_count,
            ),
        )
        return best.prompt_version or DEFAULT_PROMPT_VERSION

    def recommended_max_chars(
        self,
        *,
        model: str,
        task_type: str,
        profile: str = DEFAULT_PROFILE,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        provider: str = DEFAULT_PROVIDER,
        fallback: int = DEFAULT_RECOMMENDED_MAX_CHARS,
    ) -> int:
        stats = self.get_profile(
            model=model,
            task_type=task_type,
            profile=profile,
            prompt_version=prompt_version,
            provider=provider,
        )
        return int(fallback if stats is None else stats.recommended_max_chars)

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        ensure_model_profiles_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def ensure_model_profiles_schema(connection: sqlite3.Connection) -> None:
    """Ensure the advanced model_profiles schema on an existing connection."""
    table_exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'model_profiles'
        """
    ).fetchone()
    if table_exists is None:
        _create_advanced_table(connection)
        _normalize_profile_bounds(connection)
        return

    columns = _table_columns(connection, "model_profiles")
    if not set(ADVANCED_COLUMNS).issubset(columns):
        _migrate_legacy_table(connection)
    _normalize_profile_bounds(connection)


def profile_from_row(row: sqlite3.Row) -> ModelProfileStats:
    return ModelProfileStats(
        model=str(row["model"]),
        provider=str(row["provider"] or DEFAULT_PROVIDER),
        task_type=str(row["task_type"]),
        profile=str(row["profile"] or DEFAULT_PROFILE),
        prompt_version=str(row["prompt_version"] or DEFAULT_PROMPT_VERSION),
        runs_count=int(row["runs_count"] or 0),
        success_count=int(row["success_count"] or 0),
        json_valid_count=int(row["json_valid_count"] or 0),
        json_repaired_count=int(row["json_repaired_count"] or 0),
        json_failed_count=int(row["json_failed_count"] or row["json_fail_count"] or 0),
        model_failed_count=int(row["model_failed_count"] or 0),
        read_failed_count=int(row["read_failed_count"] or 0),
        truncated_count=int(row["truncated_count"] or 0),
        average_response_ms=float(row["average_response_ms"] or 0),
        average_input_chars=float(row["average_input_chars"] or 0),
        average_output_chars=float(row["average_output_chars"] or 0),
        recommended_max_chars=_clamp_recommended_max_chars(
            int(row["recommended_max_chars"] or DEFAULT_RECOMMENDED_MAX_CHARS)
        ),
        recommended_prompt_version=str(row["recommended_prompt_version"] or DEFAULT_PROMPT_VERSION),
        last_error=str(row["last_error"] or ""),
        last_seen_at=str(row["last_seen_at"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _create_advanced_table(connection: sqlite3.Connection) -> None:
    column_sql = ",\n                    ".join(
        f"{name} {definition}" for name, definition in ADVANCED_COLUMNS.items()
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS model_profiles (
            {column_sql},
            UNIQUE(model, provider, task_type, profile, prompt_version)
        )
        """
    )


def _migrate_legacy_table(connection: sqlite3.Connection) -> None:
    legacy_name = _unique_legacy_table_name(connection)
    connection.execute(f"ALTER TABLE model_profiles RENAME TO {legacy_name}")
    _create_advanced_table(connection)
    legacy_columns = _table_columns(connection, legacy_name)
    legacy_rows = connection.execute(f"SELECT * FROM {legacy_name}").fetchall()
    for row in legacy_rows:
        now = _utc_now()
        success_count = _row_int(row, legacy_columns, "success_count")
        json_fail_count = _row_int(row, legacy_columns, "json_fail_count")
        json_repair_count = _row_int(row, legacy_columns, "json_repair_count")
        runs_count = success_count + json_fail_count
        average_response_time = _row_float(row, legacy_columns, "average_response_time")
        average_response_ms = average_response_time * 1000
        updated_at = _row_str(row, legacy_columns, "updated_at") or now
        model = _row_str(row, legacy_columns, "model") or "unknown-model"
        task_type = _row_str(row, legacy_columns, "task_type") or "inspect_unknown_file"
        connection.execute(
            """
            INSERT INTO model_profiles (
                model,
                provider,
                task_type,
                profile,
                prompt_version,
                runs_count,
                success_count,
                json_valid_count,
                json_repaired_count,
                json_failed_count,
                model_failed_count,
                read_failed_count,
                truncated_count,
                average_response_ms,
                average_input_chars,
                average_output_chars,
                recommended_max_chars,
                recommended_prompt_version,
                last_error,
                last_seen_at,
                created_at,
                updated_at,
                json_fail_count,
                json_repair_count,
                average_response_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model,
                DEFAULT_PROVIDER,
                task_type,
                _row_str(row, legacy_columns, "profile") or DEFAULT_PROFILE,
                _row_str(row, legacy_columns, "prompt_version") or DEFAULT_PROMPT_VERSION,
                runs_count,
                success_count,
                success_count,
                json_repair_count,
                json_fail_count,
                _row_int(row, legacy_columns, "model_failed_count"),
                _row_int(row, legacy_columns, "read_failed_count"),
                _row_int(row, legacy_columns, "truncated_count"),
                average_response_ms,
                _row_float(row, legacy_columns, "average_input_chars"),
                _row_float(row, legacy_columns, "average_output_chars"),
                _clamp_recommended_max_chars(
                    _row_int(row, legacy_columns, "recommended_max_chars") or DEFAULT_RECOMMENDED_MAX_CHARS
                ),
                _row_str(row, legacy_columns, "recommended_prompt_version") or DEFAULT_PROMPT_VERSION,
                _row_str(row, legacy_columns, "last_error"),
                _row_str(row, legacy_columns, "last_seen_at") or updated_at,
                _row_str(row, legacy_columns, "created_at") or updated_at,
                updated_at,
                json_fail_count,
                json_repair_count,
                average_response_time,
            ),
        )


def _unique_legacy_table_name(connection: sqlite3.Connection) -> str:
    base = "model_profiles_legacy"
    name = base
    index = 1
    while connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone():
        index += 1
        name = f"{base}_{index}"
    return name


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _row_int(row: sqlite3.Row, columns: set[str], column: str) -> int:
    if column not in columns:
        return 0
    return int(row[column] or 0)


def _row_float(row: sqlite3.Row, columns: set[str], column: str) -> float:
    if column not in columns:
        return 0.0
    return float(row[column] or 0)


def _row_str(row: sqlite3.Row, columns: set[str], column: str) -> str:
    if column not in columns:
        return ""
    return str(row[column] or "")


def _normalize_event(event: ModelProfileEvent) -> ModelProfileEvent:
    return ModelProfileEvent(
        model=event.model or "unknown-model",
        provider=event.provider or DEFAULT_PROVIDER,
        task_type=event.task_type or "inspect_unknown_file",
        profile=event.profile or DEFAULT_PROFILE,
        prompt_version=_normalize_prompt_version(event.prompt_version),
        status=event.status or "completed",
        json_valid=bool(event.json_valid),
        json_repaired=bool(event.json_repaired),
        truncated=bool(event.truncated),
        response_time_ms=event.response_time_ms,
        input_chars=max(0, int(event.input_chars or 0)),
        output_chars=max(0, int(event.output_chars or 0)),
        current_max_chars=event.current_max_chars,
        error=str(event.error or ""),
    )


def _normalize_profile_bounds(connection: sqlite3.Connection) -> None:
    connection.execute(
        "UPDATE model_profiles SET recommended_max_chars = ? WHERE recommended_max_chars < ?",
        (MIN_RECOMMENDED_MAX_CHARS, MIN_RECOMMENDED_MAX_CHARS),
    )
    connection.execute(
        "UPDATE model_profiles SET recommended_max_chars = ? WHERE recommended_max_chars > ?",
        (MAX_RECOMMENDED_MAX_CHARS, MAX_RECOMMENDED_MAX_CHARS),
    )


def _normalize_prompt_version(prompt_version: str | None) -> str:
    version = str(prompt_version or "").strip()
    if not version or version == "file-analysis-v1":
        return DEFAULT_PROMPT_VERSION
    return version


def _clamp_recommended_max_chars(value: int) -> int:
    return max(MIN_RECOMMENDED_MAX_CHARS, min(MAX_RECOMMENDED_MAX_CHARS, int(value)))


def _is_success(event: ModelProfileEvent) -> bool:
    return event.status in {"completed", "reused"} and event.json_valid


def _is_json_failure(event: ModelProfileEvent) -> bool:
    return event.status == "failed_json" or (
        event.status == "completed" and not event.json_valid and event.status not in {"failed_model", "failed_read"}
    )


def _average(previous_average: float, previous_total: int, new_value: float | int | None) -> float:
    if new_value is None:
        return float(previous_average)
    if previous_total <= 0:
        return float(new_value)
    return ((float(previous_average) * previous_total) + float(new_value)) / (previous_total + 1)


def _adapt_recommended_max_chars(
    *,
    current_max_chars: int,
    json_valid: bool,
    json_repaired: bool,
) -> int:
    if not json_valid:
        return max(MIN_RECOMMENDED_MAX_CHARS, int(current_max_chars * 0.75))
    if json_repaired:
        return max(MIN_RECOMMENDED_MAX_CHARS, int(current_max_chars))
    return min(MAX_RECOMMENDED_MAX_CHARS, int(current_max_chars) + SUCCESS_GROWTH_CHARS)


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(part) / float(total), 4)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
