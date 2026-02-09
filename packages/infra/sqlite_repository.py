"""SQLite-backed minimal implementation of JobRepository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import JobRepository
from .models import JobRecord, ProjectRecord, UserCookieRecord


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteJobRepository(JobRepository):
    """Minimal SQLite repository for project/job state."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row

    def ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
              project_id TEXT PRIMARY KEY,
              title TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              status TEXT NOT NULL,
              stage TEXT,
              error_code TEXT,
              error_message TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);

            CREATE TABLE IF NOT EXISTS user_cookies (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              name TEXT NOT NULL,
              cookie_encrypted TEXT NOT NULL,
              is_default INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              last_validated_at TEXT,
              last_error_code TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_user_cookies_user_id ON user_cookies(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_cookies_user_default
            ON user_cookies(user_id, is_default);
            """
        )
        self._conn.commit()

    def upsert_project(self, project_id: str, *, title: str | None, status: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO projects (project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id)
            DO UPDATE SET
              title = excluded.title,
              status = excluded.status,
              updated_at = excluded.updated_at
            """,
            (project_id, title, status, now, now),
        )
        self._conn.commit()

    def get_project(self, project_id: str) -> ProjectRecord | None:
        row = self._conn.execute(
            """
            SELECT project_id, title, status, created_at, updated_at
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return ProjectRecord(
            project_id=row["project_id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_project_status(self, project_id: str, status: str) -> None:
        self._conn.execute(
            """
            UPDATE projects
            SET status = ?, updated_at = ?
            WHERE project_id = ?
            """,
            (status, _utc_now_iso(), project_id),
        )
        self._conn.commit()

    def create_job(
        self, job_id: str, project_id: str, *, status: str, stage: str | None = None
    ) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO jobs (
              job_id,
              project_id,
              status,
              stage,
              error_code,
              error_message,
              created_at,
              updated_at
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (job_id, project_id, status, stage, now, now),
        )
        self._conn.commit()

    def get_job(self, job_id: str) -> JobRecord | None:
        row = self._conn.execute(
            """
            SELECT
              job_id,
              project_id,
              status,
              stage,
              error_code,
              error_message,
              created_at,
              updated_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return JobRecord(
            job_id=row["job_id"],
            project_id=row["project_id"],
            status=row["status"],
            stage=row["stage"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_jobs_for_project(self, project_id: str) -> list[JobRecord]:
        rows = self._conn.execute(
            """
            SELECT
              job_id,
              project_id,
              status,
              stage,
              error_code,
              error_message,
              created_at,
              updated_at
            FROM jobs
            WHERE project_id = ?
            ORDER BY created_at ASC
            """,
            (project_id,),
        ).fetchall()
        return [
            JobRecord(
                job_id=row["job_id"],
                project_id=row["project_id"],
                status=row["status"],
                stage=row["stage"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        stage: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        current = self.get_job(job_id)
        if current is None:
            return

        self._conn.execute(
            """
            UPDATE jobs
            SET
              status = ?,
              stage = ?,
              error_code = ?,
              error_message = ?,
              updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                stage if stage is not None else current.stage,
                error_code,
                error_message,
                _utc_now_iso(),
                job_id,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create_user_cookie(
        self,
        *,
        cookie_id: str,
        user_id: str,
        name: str,
        cookie_encrypted: str,
        is_default: bool,
        status: str,
    ) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO user_cookies (
              id,
              user_id,
              name,
              cookie_encrypted,
              is_default,
              status,
              last_validated_at,
              last_error_code,
              created_at,
              updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                cookie_id,
                user_id,
                name,
                cookie_encrypted,
                1 if is_default else 0,
                status,
                now,
                now,
            ),
        )
        self._conn.commit()

    def list_user_cookies(self, user_id: str) -> list[UserCookieRecord]:
        rows = self._conn.execute(
            """
            SELECT
              id,
              user_id,
              name,
              cookie_encrypted,
              is_default,
              status,
              last_validated_at,
              last_error_code,
              created_at,
              updated_at
            FROM user_cookies
            WHERE user_id = ?
            ORDER BY created_at ASC
            """,
            (user_id,),
        ).fetchall()
        return [self._to_user_cookie_record(row) for row in rows]

    def get_user_cookie(self, cookie_id: str, user_id: str) -> UserCookieRecord | None:
        row = self._conn.execute(
            """
            SELECT
              id,
              user_id,
              name,
              cookie_encrypted,
              is_default,
              status,
              last_validated_at,
              last_error_code,
              created_at,
              updated_at
            FROM user_cookies
            WHERE id = ? AND user_id = ?
            """,
            (cookie_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return self._to_user_cookie_record(row)

    def update_user_cookie(
        self,
        *,
        cookie_id: str,
        user_id: str,
        name: str | None = None,
        cookie_encrypted: str | None = None,
        is_default: bool | None = None,
        status: str | None = None,
        last_validated_at: str | None = None,
        last_error_code: str | None = None,
        set_last_validated_at: bool = False,
        set_last_error_code: bool = False,
    ) -> None:
        current = self.get_user_cookie(cookie_id, user_id)
        if current is None:
            return

        self._conn.execute(
            """
            UPDATE user_cookies
            SET
              name = ?,
              cookie_encrypted = ?,
              is_default = ?,
              status = ?,
              last_validated_at = ?,
              last_error_code = ?,
              updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                name if name is not None else current.name,
                cookie_encrypted if cookie_encrypted is not None else current.cookie_encrypted,
                (1 if is_default else 0)
                if is_default is not None
                else (1 if current.is_default else 0),
                status if status is not None else current.status,
                last_validated_at if set_last_validated_at else current.last_validated_at,
                last_error_code if set_last_error_code else current.last_error_code,
                _utc_now_iso(),
                cookie_id,
                user_id,
            ),
        )
        self._conn.commit()

    def delete_user_cookie(self, cookie_id: str, user_id: str) -> None:
        self._conn.execute(
            """
            DELETE FROM user_cookies
            WHERE id = ? AND user_id = ?
            """,
            (cookie_id, user_id),
        )
        self._conn.commit()

    def clear_default_cookie_for_user(self, user_id: str) -> None:
        self._conn.execute(
            """
            UPDATE user_cookies
            SET is_default = 0, updated_at = ?
            WHERE user_id = ? AND is_default = 1
            """,
            (_utc_now_iso(), user_id),
        )
        self._conn.commit()

    def _to_user_cookie_record(self, row: sqlite3.Row) -> UserCookieRecord:
        return UserCookieRecord(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            cookie_encrypted=row["cookie_encrypted"],
            is_default=bool(row["is_default"]),
            status=row["status"],
            last_validated_at=row["last_validated_at"],
            last_error_code=row["last_error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
