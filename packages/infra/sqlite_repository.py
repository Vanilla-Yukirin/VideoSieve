"""SQLite-backed minimal implementation of JobRepository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import JobRepository
from .models import JobRecord, ProjectRecord


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
