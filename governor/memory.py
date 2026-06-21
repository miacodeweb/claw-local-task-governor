"""SQLite memory for reusable file task results."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MEMORY_PATH = Path("data") / "memory.sqlite"
DEFAULT_RECOMMENDED_MAX_CHARS = 12000
MIN_RECOMMENDED_MAX_CHARS = 2000
MAX_RECOMMENDED_MAX_CHARS = 24000
SUCCESS_GROWTH_CHARS = 500


@dataclass(frozen=True)
class ReusableTaskResult:
    file_path: str
    file_hash: str
    task_type: str
    model: str
    prompt_version: str
    json_valid: bool
    json_repaired: bool
    risk: str
    result_json: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ModelProfileStats:
    model: str
    task_type: str
    success_count: int
    json_fail_count: int
    json_repair_count: int
    average_response_time: float
    recommended_max_chars: int
    updated_at: str


class SQLiteMemory:
    """Small SQLite-backed memory for project files and task results."""

    def __init__(self, db_path: Path | str = DEFAULT_MEMORY_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_project(self, path: str, project_type: str | None = None) -> int:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM projects WHERE path = ?",
                (path,),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE projects SET project_type = ?, last_seen_at = ? WHERE id = ?",
                    (project_type, now, row["id"]),
                )
                return int(row["id"])

            cursor = connection.execute(
                """
                INSERT INTO projects (path, project_type, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (path, project_type, now, now),
            )
            return int(cursor.lastrowid)

    def upsert_file(
        self,
        project_id: int,
        path: str,
        file_hash: str,
        size: int | None = None,
        extension: str | None = None,
        importance: str | None = None,
    ) -> int:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM files WHERE project_id = ? AND path = ?",
                (project_id, path),
            ).fetchone()
            if row:
                connection.execute(
                    """
                    UPDATE files
                    SET hash = ?, size = ?, extension = ?, importance = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (file_hash, size, extension, importance, now, row["id"]),
                )
                return int(row["id"])

            cursor = connection.execute(
                """
                INSERT INTO files (project_id, path, hash, size, extension, importance, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, path, file_hash, size, extension, importance, now),
            )
            return int(cursor.lastrowid)

    def find_reusable_result(
        self,
        *,
        project_path: str,
        file_path: str,
        file_hash: str,
        task_type: str,
        model: str,
        prompt_version: str,
    ) -> ReusableTaskResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT tr.*
                FROM task_results tr
                JOIN projects p ON p.id = tr.project_id
                WHERE p.path = ?
                  AND tr.file_path = ?
                  AND tr.file_hash = ?
                  AND tr.task_type = ?
                  AND tr.model = ?
                  AND tr.prompt_version = ?
                  AND tr.json_valid = 1
                ORDER BY tr.created_at DESC, tr.id DESC
                LIMIT 1
                """,
                (project_path, file_path, file_hash, task_type, model, prompt_version),
            ).fetchone()

        if row is None:
            return None

        return ReusableTaskResult(
            file_path=str(row["file_path"]),
            file_hash=str(row["file_hash"]),
            task_type=str(row["task_type"]),
            model=str(row["model"]),
            prompt_version=str(row["prompt_version"]),
            json_valid=bool(row["json_valid"]),
            json_repaired=bool(row["json_repaired"]),
            risk=str(row["risk"]),
            result_json=json.loads(row["result_json"]),
            created_at=str(row["created_at"]),
        )

    def save_task_result(
        self,
        *,
        project_path: str,
        project_type: str | None,
        file_path: str,
        file_hash: str,
        task_type: str,
        model: str,
        prompt_version: str,
        json_valid: bool,
        json_repaired: bool,
        risk: str,
        result_json: dict[str, Any] | None,
        response_time_seconds: float | None = None,
        current_max_chars: int | None = None,
    ) -> int:
        project_id = self.upsert_project(project_path, project_type)
        self.upsert_file(project_id, file_path, file_hash)
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO task_results (
                    project_id,
                    file_path,
                    file_hash,
                    task_type,
                    model,
                    prompt_version,
                    json_valid,
                    json_repaired,
                    risk,
                    result_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    file_path,
                    file_hash,
                    task_type,
                    model,
                    prompt_version,
                    1 if json_valid else 0,
                    1 if json_repaired else 0,
                    risk,
                    json.dumps(result_json or {}, sort_keys=True),
                    now,
                ),
            )
            self.update_model_profile(
                model=model,
                task_type=task_type,
                json_valid=json_valid,
                json_repaired=json_repaired,
                response_time_seconds=response_time_seconds,
                current_max_chars=current_max_chars,
                connection=connection,
            )
            return int(cursor.lastrowid)

    def update_model_profile(
        self,
        *,
        model: str,
        task_type: str,
        json_valid: bool,
        json_repaired: bool,
        response_time_seconds: float | None = None,
        current_max_chars: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        close_connection = connection is None
        conn = connection or self._connect()
        try:
            now = _utc_now()
            row = conn.execute(
                """
                SELECT id,
                       success_count,
                       json_fail_count,
                       json_repair_count,
                       average_response_time,
                       recommended_max_chars
                FROM model_profiles
                WHERE model = ? AND task_type = ?
                """,
                (model, task_type),
            ).fetchone()
            base_max_chars = int(current_max_chars or DEFAULT_RECOMMENDED_MAX_CHARS)
            if row is None:
                recommended_max_chars = _adapt_recommended_max_chars(
                    current_max_chars=base_max_chars,
                    json_valid=json_valid,
                    json_repaired=json_repaired,
                )
                conn.execute(
                    """
                    INSERT INTO model_profiles (
                        model,
                        task_type,
                        success_count,
                        json_fail_count,
                        json_repair_count,
                        average_response_time,
                        recommended_max_chars,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        model,
                        task_type,
                        1 if json_valid else 0,
                        0 if json_valid else 1,
                        1 if json_repaired else 0,
                        float(response_time_seconds or 0),
                        recommended_max_chars,
                        now,
                    ),
                )
            else:
                previous_total = int(row["success_count"]) + int(row["json_fail_count"])
                average_response_time = _update_average_response_time(
                    previous_average=float(row["average_response_time"] or 0),
                    previous_total=previous_total,
                    response_time_seconds=response_time_seconds,
                )
                recommended_max_chars = _adapt_recommended_max_chars(
                    current_max_chars=int(row["recommended_max_chars"] or base_max_chars),
                    json_valid=json_valid,
                    json_repaired=json_repaired,
                )
                conn.execute(
                    """
                    UPDATE model_profiles
                    SET success_count = success_count + ?,
                        json_fail_count = json_fail_count + ?,
                        json_repair_count = json_repair_count + ?,
                        average_response_time = ?,
                        recommended_max_chars = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        1 if json_valid else 0,
                        0 if json_valid else 1,
                        1 if json_repaired else 0,
                        average_response_time,
                        recommended_max_chars,
                        now,
                        row["id"],
                    ),
                )
        finally:
            if close_connection:
                conn.commit()
                conn.close()

    def get_model_profile(self, model: str, task_type: str) -> ModelProfileStats | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT model,
                       task_type,
                       success_count,
                       json_fail_count,
                       json_repair_count,
                       average_response_time,
                       recommended_max_chars,
                       updated_at
                FROM model_profiles
                WHERE model = ? AND task_type = ?
                """,
                (model, task_type),
            ).fetchone()
        return _profile_from_row(row) if row is not None else None

    def list_model_profiles(self) -> list[ModelProfileStats]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT model,
                       task_type,
                       success_count,
                       json_fail_count,
                       json_repair_count,
                       average_response_time,
                       recommended_max_chars,
                       updated_at
                FROM model_profiles
                ORDER BY model, task_type
                """
            ).fetchall()
        return [_profile_from_row(row) for row in rows]

    def recommended_max_chars(
        self,
        model: str,
        task_type: str,
        fallback: int = DEFAULT_RECOMMENDED_MAX_CHARS,
    ) -> int:
        profile = self.get_model_profile(model, task_type)
        if profile is None:
            return int(fallback)
        return profile.recommended_max_chars

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    project_type TEXT,
                    created_at TEXT,
                    last_seen_at TEXT
                );

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    path TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    size INTEGER,
                    extension TEXT,
                    importance TEXT,
                    last_seen_at TEXT,
                    UNIQUE(project_id, path)
                );

                CREATE TABLE IF NOT EXISTS task_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    file_path TEXT,
                    file_hash TEXT,
                    task_type TEXT,
                    model TEXT,
                    prompt_version TEXT,
                    json_valid INTEGER,
                    json_repaired INTEGER,
                    risk TEXT,
                    result_json TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS model_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT,
                    task_type TEXT,
                    success_count INTEGER DEFAULT 0,
                    json_fail_count INTEGER DEFAULT 0,
                    json_repair_count INTEGER DEFAULT 0,
                    average_response_time REAL DEFAULT 0,
                    recommended_max_chars INTEGER DEFAULT 12000,
                    updated_at TEXT,
                    UNIQUE(model, task_type)
                );
                """
            )
            _ensure_column(connection, "model_profiles", "average_response_time", "REAL DEFAULT 0")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _update_average_response_time(
    *,
    previous_average: float,
    previous_total: int,
    response_time_seconds: float | None,
) -> float:
    if response_time_seconds is None:
        return previous_average
    if previous_total <= 0:
        return float(response_time_seconds)
    return ((previous_average * previous_total) + float(response_time_seconds)) / (previous_total + 1)


def _profile_from_row(row: sqlite3.Row) -> ModelProfileStats:
    return ModelProfileStats(
        model=str(row["model"]),
        task_type=str(row["task_type"]),
        success_count=int(row["success_count"]),
        json_fail_count=int(row["json_fail_count"]),
        json_repair_count=int(row["json_repair_count"]),
        average_response_time=float(row["average_response_time"] or 0),
        recommended_max_chars=int(row["recommended_max_chars"]),
        updated_at=str(row["updated_at"]),
    )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
