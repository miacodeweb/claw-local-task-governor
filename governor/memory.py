"""SQLite memory for reusable file task results."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json

from governor.model_profiles import (
    DEFAULT_RECOMMENDED_MAX_CHARS,
    MAX_RECOMMENDED_MAX_CHARS,
    MIN_RECOMMENDED_MAX_CHARS,
    SUCCESS_GROWTH_CHARS,
    ModelProfileEvent,
    ModelProfileStats,
    ModelProfileStore,
    ensure_model_profiles_schema,
)


DEFAULT_MEMORY_PATH = Path("data") / "memory.sqlite"


@dataclass(frozen=True)
class ReusableTaskResult:
    project_path: str
    task_id: str
    file_path: str
    file_hash: str
    task_type: str
    profile: str
    model: str
    prompt_version: str
    status: str
    json_valid: bool
    json_repaired: bool
    truncated: bool
    risk: str
    raw_response: str
    result_json: dict[str, Any] | None
    errors: list[str]
    created_at: str


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
                WHERE tr.project_path = ?
                  AND tr.file_path = ?
                  AND tr.file_hash = ?
                  AND tr.task_type = ?
                  AND tr.model = ?
                  AND tr.prompt_version = ?
                  AND tr.json_valid = 1
                  AND tr.status = 'completed'
                ORDER BY tr.created_at DESC, tr.id DESC
                LIMIT 1
                """,
                (project_path, file_path, file_hash, task_type, model, prompt_version),
            ).fetchone()

        if row is None:
            return None

        return ReusableTaskResult(
            project_path=str(row["project_path"]),
            task_id=str(row["task_id"] or ""),
            file_path=str(row["file_path"]),
            file_hash=str(row["file_hash"]),
            task_type=str(row["task_type"]),
            profile=str(row["profile"] or "general"),
            model=str(row["model"]),
            prompt_version=str(row["prompt_version"]),
            status=str(row["status"] or "completed"),
            json_valid=bool(row["json_valid"]),
            json_repaired=bool(row["json_repaired"]),
            truncated=bool(row["truncated"]),
            risk=str(row["risk"]),
            raw_response=str(row["raw_response"] or ""),
            result_json=json.loads(row["result_json"]) if row["result_json"] else None,
            errors=json.loads(row["errors_json"]) if row["errors_json"] else [],
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
        task_id: str = "",
        profile: str = "general",
        status: str = "completed",
        truncated: bool = False,
        raw_response: str = "",
        errors: list[str] | None = None,
        created_at: str | None = None,
        response_time_seconds: float | None = None,
        current_max_chars: int | None = None,
        input_chars: int = 0,
        output_chars: int = 0,
    ) -> int:
        project_id = self.upsert_project(project_path, project_type)
        self.upsert_file(project_id, file_path, file_hash)
        now = created_at or _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO task_results (
                    project_id,
                    project_path,
                    file_path,
                    file_hash,
                    task_id,
                    task_type,
                    profile,
                    model,
                    prompt_version,
                    status,
                    json_valid,
                    json_repaired,
                    truncated,
                    risk,
                    raw_response,
                    result_json,
                    errors_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    project_path,
                    file_path,
                    file_hash,
                    task_id,
                    task_type,
                    profile,
                    model,
                    prompt_version,
                    status,
                    1 if json_valid else 0,
                    1 if json_repaired else 0,
                    1 if truncated else 0,
                    risk,
                    raw_response,
                    json.dumps(result_json or {}, sort_keys=True),
                    json.dumps(errors or [], sort_keys=True),
                    now,
                ),
            )
            self.update_model_profile(
                model=model,
                task_type=task_type,
                profile=profile,
                prompt_version=prompt_version,
                status=status,
                json_valid=json_valid,
                json_repaired=json_repaired,
                truncated=truncated,
                response_time_seconds=response_time_seconds,
                current_max_chars=current_max_chars,
                input_chars=input_chars,
                output_chars=output_chars,
                error=(errors or [""])[0] if errors else "",
                connection=connection,
            )
            return int(cursor.lastrowid)

    def update_model_profile(
        self,
        *,
        model: str,
        task_type: str,
        profile: str = "general",
        prompt_version: str = "file-analysis-v1",
        status: str = "completed",
        json_valid: bool,
        json_repaired: bool,
        truncated: bool = False,
        response_time_seconds: float | None = None,
        current_max_chars: int | None = None,
        input_chars: int = 0,
        output_chars: int = 0,
        error: str = "",
        connection: sqlite3.Connection | None = None,
    ) -> None:
        close_connection = connection is None
        conn = connection or self._connect()
        try:
            store = object.__new__(ModelProfileStore)
            store.db_path = self.db_path
            store.record_task_result_with_connection(
                conn,
                ModelProfileEvent(
                    model=model,
                    task_type=task_type,
                    profile=profile,
                    prompt_version=prompt_version,
                    status=status,
                    json_valid=json_valid,
                    json_repaired=json_repaired,
                    truncated=truncated,
                    response_time_ms=None
                    if response_time_seconds is None
                    else float(response_time_seconds) * 1000,
                    input_chars=input_chars,
                    output_chars=output_chars,
                    current_max_chars=current_max_chars,
                    error=error,
                ),
            )
        finally:
            if close_connection:
                conn.commit()
                conn.close()

    def get_model_profile(self, model: str, task_type: str) -> ModelProfileStats | None:
        store = ModelProfileStore(self.db_path)
        return store.get_profile(model=model, task_type=task_type)

    def list_model_profiles(self) -> list[ModelProfileStats]:
        store = ModelProfileStore(self.db_path)
        return store.list_profiles()

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

    def model_profile_store(self) -> ModelProfileStore:
        return ModelProfileStore(self.db_path)

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
                    project_path TEXT,
                    file_path TEXT,
                    file_hash TEXT,
                    task_id TEXT,
                    task_type TEXT,
                    profile TEXT,
                    model TEXT,
                    prompt_version TEXT,
                    status TEXT,
                    json_valid INTEGER,
                    json_repaired INTEGER,
                    truncated INTEGER DEFAULT 0,
                    risk TEXT,
                    raw_response TEXT,
                    result_json TEXT,
                    errors_json TEXT,
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
            _ensure_column(connection, "task_results", "project_path", "TEXT")
            _ensure_column(connection, "task_results", "task_id", "TEXT")
            _ensure_column(connection, "task_results", "profile", "TEXT")
            _ensure_column(connection, "task_results", "status", "TEXT")
            _ensure_column(connection, "task_results", "truncated", "INTEGER DEFAULT 0")
            _ensure_column(connection, "task_results", "raw_response", "TEXT")
            _ensure_column(connection, "task_results", "errors_json", "TEXT")
            connection.execute(
                """
                UPDATE task_results
                SET project_path = (
                    SELECT projects.path FROM projects WHERE projects.id = task_results.project_id
                )
                WHERE project_path IS NULL
                """
            )
            connection.execute("UPDATE task_results SET profile = 'general' WHERE profile IS NULL")
            connection.execute("UPDATE task_results SET status = 'completed' WHERE status IS NULL")
            connection.execute("UPDATE task_results SET truncated = 0 WHERE truncated IS NULL")
            connection.execute("UPDATE task_results SET raw_response = '' WHERE raw_response IS NULL")
            connection.execute("UPDATE task_results SET errors_json = '[]' WHERE errors_json IS NULL")
            ensure_model_profiles_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
