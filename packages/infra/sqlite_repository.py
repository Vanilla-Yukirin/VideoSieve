"""SQLite-backed minimal implementation of JobRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import JobRepository
from .models import (
    AuthUserRecord,
    InfraEvent,
    JobRecord,
    OperationLogRecord,
    ProjectRecord,
    UserCookieRecord,
    parse_iso8601,
)

GLOBAL_GUEST_COOLDOWN_KEY = "global_guest_job_cooldown"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteJobRepository(JobRepository):
    """Minimal SQLite repository for project/job state."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")

    @property
    def db_path(self) -> Path:
        """Return the backing database path for sibling process adapters."""

        return self._db_path

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
              delete_pending INTEGER NOT NULL DEFAULT 0,
              worker_id TEXT,
              attempt INTEGER NOT NULL DEFAULT 0,
              claimed_at TEXT,
              heartbeat_at TEXT,
              control_command TEXT,
              control_version INTEGER NOT NULL DEFAULT 0,
              control_ack_version INTEGER NOT NULL DEFAULT 0,
              control_requested_at TEXT,
              control_acknowledged_at TEXT,
              control_request_id TEXT,
              state_version INTEGER NOT NULL DEFAULT 0,
              progress REAL NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
            CREATE TABLE IF NOT EXISTS job_events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL,
              event_type TEXT NOT NULL,
              project_id TEXT NOT NULL,
              job_id TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              ts TEXT NOT NULL,
              state_version INTEGER NOT NULL DEFAULT 0,
              request_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_job_events_channel_cursor
            ON job_events(channel, event_id);

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

            CREATE TABLE IF NOT EXISTS system_settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_user (
              id TEXT PRIMARY KEY,
              username TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operation_logs (
              id TEXT PRIMARY KEY,
              actor_type TEXT NOT NULL,
              actor_id TEXT,
              action TEXT NOT NULL,
              status TEXT NOT NULL,
              reason_code TEXT,
              created_at TEXT NOT NULL,
              meta_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
            ON operation_logs(created_at DESC);

            CREATE TABLE IF NOT EXISTS guest_cooldown (
              key TEXT PRIMARY KEY,
              next_allowed_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        job_columns = {
            str(row[1])
            for row in self._conn.execute("PRAGMA table_info(jobs)").fetchall()
            if len(row) > 1
        }
        migrations = {
            "delete_pending": "INTEGER NOT NULL DEFAULT 0",
            "worker_id": "TEXT",
            "attempt": "INTEGER NOT NULL DEFAULT 0",
            "claimed_at": "TEXT",
            "heartbeat_at": "TEXT",
            "control_command": "TEXT",
            "control_version": "INTEGER NOT NULL DEFAULT 0",
            "control_ack_version": "INTEGER NOT NULL DEFAULT 0",
            "control_requested_at": "TEXT",
            "control_acknowledged_at": "TEXT",
            "control_request_id": "TEXT",
            "state_version": "INTEGER NOT NULL DEFAULT 0",
            "progress": "REAL NOT NULL DEFAULT 0",
        }
        for column, declaration in migrations.items():
            if column not in job_columns:
                self._conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {declaration}")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(status, created_at)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_heartbeat ON jobs(status, heartbeat_at)"
        )
        event_columns = {
            str(row[1])
            for row in self._conn.execute("PRAGMA table_info(job_events)").fetchall()
            if len(row) > 1
        }
        event_migrations = {
            "state_version": "INTEGER NOT NULL DEFAULT 0",
            "request_id": "TEXT",
        }
        for column, declaration in event_migrations.items():
            if column not in event_columns:
                self._conn.execute(
                    f"ALTER TABLE job_events ADD COLUMN {column} {declaration}"
                )
        legacy_now = _utc_now_iso()
        self._conn.execute(
            """
            UPDATE jobs
            SET
              control_command = 'pause',
              control_version = CASE WHEN control_version < 1 THEN 1 ELSE control_version END,
              control_requested_at = COALESCE(control_requested_at, ?),
              status = CASE WHEN worker_id IS NULL THEN 'interrupted' ELSE 'running' END,
              state_version = state_version + 1,
              updated_at = ?
            WHERE status = 'pause_requested'
            """,
            (legacy_now, legacy_now),
        )
        self._conn.execute(
            """
            UPDATE jobs
            SET
              control_command = 'cancel',
              control_version = CASE WHEN control_version < 1 THEN 1 ELSE control_version END,
              control_requested_at = COALESCE(control_requested_at, ?),
              status = CASE WHEN worker_id IS NULL THEN 'interrupted' ELSE 'running' END,
              state_version = state_version + 1,
              updated_at = ?
            WHERE status = 'cancel_requested'
            """,
            (legacy_now, legacy_now),
        )
        self._conn.execute(
            """
            UPDATE projects
            SET status = 'interrupted', updated_at = ?
            WHERE status IN ('pause_requested', 'cancel_requested')
            """,
            (legacy_now,),
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

    def refresh_project_status(self, project_id: str) -> str | None:
        """Derive project status from all persisted jobs."""

        status = self._refresh_project_status_in_transaction(project_id, _utc_now_iso())
        self._conn.commit()
        return status

    def _refresh_project_status_in_transaction(
        self, project_id: str, now: str
    ) -> str | None:
        rows = self._conn.execute(
            "SELECT status FROM jobs WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        if not rows:
            return None
        statuses = {str(row["status"]) for row in rows}
        precedence = (
            "running",
            "queued",
            "paused",
            "interrupted",
            "failed",
            "cancelled",
            "succeeded",
        )
        status = next(item for item in precedence if item in statuses)
        self._conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE project_id = ?",
            (status, now, project_id),
        )
        return status

    def delete_project(self, project_id: str) -> None:
        self._conn.execute(
            """
            DELETE FROM job_events
            WHERE job_id IN (SELECT job_id FROM jobs WHERE project_id = ?)
            """,
            (project_id,),
        )
        self._conn.execute(
            """
            DELETE FROM jobs
            WHERE project_id = ?
            """,
            (project_id,),
        )
        self._conn.execute(
            """
            DELETE FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
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
              delete_pending,
              worker_id,
              attempt,
              claimed_at,
              heartbeat_at,
              control_command,
              control_version,
              control_ack_version,
              control_requested_at,
              control_acknowledged_at,
              control_request_id,
              state_version,
              progress,
              created_at,
              updated_at
            )
            VALUES (
              ?, ?, ?, ?, NULL, NULL, 0, NULL, 0, NULL,
              NULL, NULL, 0, 0, NULL, NULL, NULL, 0, 0, ?, ?
            )
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
              delete_pending,
              worker_id,
              attempt,
              claimed_at,
              heartbeat_at,
              control_command,
              control_version,
              control_ack_version,
              control_requested_at,
              control_acknowledged_at,
              control_request_id,
              state_version,
              progress,
              created_at,
              updated_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_job_record(row)

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
              delete_pending,
              worker_id,
              attempt,
              claimed_at,
              heartbeat_at,
              control_command,
              control_version,
              control_ack_version,
              control_requested_at,
              control_acknowledged_at,
              control_request_id,
              state_version,
              progress,
              created_at,
              updated_at
            FROM jobs
            WHERE project_id = ?
            ORDER BY created_at ASC
            """,
            (project_id,),
        ).fetchall()
        return [self._to_job_record(row) for row in rows]

    def update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        stage: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        expected_worker_id: str | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        current = self.get_job(job_id)
        if current is None:
            return False

        where = "job_id = ?"
        params: list[object] = [
            status,
            stage if stage is not None else current.stage,
            error_code,
            error_message,
            100.0 if status == "succeeded" else current.progress,
            _utc_now_iso(),
            job_id,
        ]
        if expected_worker_id is not None:
            where += " AND worker_id = ?"
            params.append(expected_worker_id)
        if expected_attempt is not None:
            where += " AND attempt = ?"
            params.append(expected_attempt)

        cursor = self._conn.execute(
            f"""
            UPDATE jobs
            SET
              status = ?,
              stage = ?,
              error_code = ?,
              error_message = ?,
              progress = ?,
              state_version = state_version + 1,
              updated_at = ?
            WHERE {where}
            """,
            tuple(params),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def update_job_progress(
        self,
        job_id: str,
        *,
        progress: float,
        stage: str | None,
        expected_worker_id: str | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        where = "job_id = ?"
        params: list[object] = [
            max(0.0, min(100.0, progress)),
            stage,
            _utc_now_iso(),
            job_id,
        ]
        if expected_worker_id is not None:
            where += " AND worker_id = ?"
            params.append(expected_worker_id)
        if expected_attempt is not None:
            where += " AND attempt = ?"
            params.append(expected_attempt)
        cursor = self._conn.execute(
            f"""
            UPDATE jobs
            SET progress = ?, stage = ?, state_version = state_version + 1, updated_at = ?
            WHERE {where}
            """,
            tuple(params),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def delete_job(self, job_id: str) -> None:
        self._conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
        self._conn.execute(
            """
            DELETE FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        )
        self._conn.commit()

    def set_job_delete_pending(self, job_id: str, pending: bool) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET delete_pending = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (1 if pending else 0, _utc_now_iso(), job_id),
        )
        self._conn.commit()

    def list_pending_delete_job_ids(self) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT job_id
            FROM jobs
            WHERE delete_pending = 1
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [str(row["job_id"]) for row in rows]

    def claim_next_job(self, worker_id: str) -> JobRecord | None:
        """Atomically lease one queued job or one paused job with a resume request."""

        now = _utc_now_iso()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """
                SELECT job_id, project_id
                FROM jobs
                WHERE
                  (
                    status = 'queued'
                    AND NOT (
                      control_command = 'cancel'
                      AND control_version > control_ack_version
                    )
                  )
                  OR (
                    status = 'paused'
                    AND control_command = 'resume'
                    AND control_version > control_ack_version
                  )
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                self._conn.commit()
                return None

            job_id = str(row["job_id"])
            project_id = str(row["project_id"])
            cursor = self._conn.execute(
                """
                UPDATE jobs
                SET
                  status = 'running',
                  worker_id = ?,
                  attempt = attempt + 1,
                  claimed_at = ?,
                  heartbeat_at = ?,
                  state_version = state_version + 1,
                  control_ack_version = CASE
                    WHEN control_command = 'resume' AND control_version > control_ack_version
                    THEN control_version
                    ELSE control_ack_version
                  END,
                  control_acknowledged_at = CASE
                    WHEN control_command = 'resume' AND control_version > control_ack_version
                    THEN ?
                    ELSE control_acknowledged_at
                  END,
                  updated_at = ?
                WHERE job_id = ?
                  AND (
                    (
                      status = 'queued'
                      AND NOT (
                        control_command = 'cancel'
                        AND control_version > control_ack_version
                      )
                    )
                    OR (
                      status = 'paused'
                      AND control_command = 'resume'
                      AND control_version > control_ack_version
                    )
                  )
                """,
                (worker_id, now, now, now, now, job_id),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                return None
            self._conn.execute(
                """
                UPDATE projects
                SET status = 'running', updated_at = ?
                WHERE project_id = ?
                """,
                (now, project_id),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return self.get_job(job_id)

    def heartbeat_job(
        self, job_id: str, worker_id: str, *, expected_attempt: int | None = None
    ) -> bool:
        where = "job_id = ? AND worker_id = ? AND status = 'running'"
        params: list[object] = [_utc_now_iso(), job_id, worker_id]
        if expected_attempt is not None:
            where += " AND attempt = ?"
            params.append(expected_attempt)
        cursor = self._conn.execute(
            f"""
            UPDATE jobs
            SET heartbeat_at = ?
            WHERE {where}
            """,
            tuple(params),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def release_job_claim(
        self, job_id: str, worker_id: str, *, expected_attempt: int | None = None
    ) -> bool:
        where = "job_id = ? AND worker_id = ?"
        params: list[object] = [_utc_now_iso(), job_id, worker_id]
        if expected_attempt is not None:
            where += " AND attempt = ?"
            params.append(expected_attempt)
        cursor = self._conn.execute(
            f"""
            UPDATE jobs
            SET worker_id = NULL, claimed_at = NULL, heartbeat_at = NULL, updated_at = ?
            WHERE {where}
            """,
            tuple(params),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def mark_stale_jobs_interrupted(self, stale_before: datetime) -> list[str]:
        """Fence stale claims by moving them to an explicit interrupted state."""

        cutoff = stale_before.isoformat()
        now = _utc_now_iso()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            rows = self._conn.execute(
                """
                SELECT job_id, project_id
                FROM jobs
                WHERE worker_id IS NOT NULL
                  AND status = 'running'
                  AND COALESCE(heartbeat_at, claimed_at) < ?
                ORDER BY created_at ASC
                """,
                (cutoff,),
            ).fetchall()
            job_ids = [str(row["job_id"]) for row in rows]
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                self._conn.execute(
                    f"""
                    UPDATE jobs
                    SET
                      status = 'interrupted',
                      worker_id = NULL,
                      claimed_at = NULL,
                      heartbeat_at = NULL,
                      state_version = state_version + 1,
                      updated_at = ?
                    WHERE job_id IN ({placeholders})
                    """,
                    (now, *job_ids),
                )
                project_ids = sorted({str(row["project_id"]) for row in rows})
                for project_id in project_ids:
                    self._refresh_project_status_in_transaction(project_id, now)
            self._conn.commit()
            return job_ids
        except Exception:
            self._conn.rollback()
            raise

    def recover_interrupted_job(
        self,
        job_id: str,
        *,
        request_id: str | None = None,
        expected_state_version: int | None = None,
    ) -> bool:
        """Explicitly return an interrupted job to the queue."""

        now = _utc_now_iso()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """
                SELECT project_id, state_version, control_version, control_request_id,
                       control_command
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                self._conn.commit()
                return False
            if request_id is not None and row["control_request_id"] == request_id:
                accepted = bool(row["control_command"] == "resume")
                self._conn.commit()
                return accepted
            status_row = self._conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if status_row is None or str(status_row["status"]) != "interrupted":
                self._conn.commit()
                return False
            if (
                expected_state_version is not None
                and int(row["state_version"]) != expected_state_version
            ):
                self._conn.commit()
                return False
            version = int(row["control_version"]) + 1
            cursor = self._conn.execute(
                """
                UPDATE jobs
                SET
                  status = 'queued',
                  worker_id = NULL,
                  claimed_at = NULL,
                  heartbeat_at = NULL,
                  control_command = 'resume',
                  control_version = ?,
                  control_requested_at = ?,
                  control_acknowledged_at = NULL,
                  control_request_id = ?,
                  error_code = NULL,
                  error_message = NULL,
                  state_version = state_version + 1,
                  updated_at = ?
                WHERE job_id = ? AND status = 'interrupted' AND state_version = ?
                """,
                (version, now, request_id, now, job_id, int(row["state_version"])),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                return False
            self._refresh_project_status_in_transaction(str(row["project_id"]), now)
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def request_job_control(
        self,
        job_id: str,
        command: str,
        *,
        request_id: str | None = None,
        expected_status: str | None = None,
        expected_state_version: int | None = None,
        finalize_cancel_if_unowned: bool = False,
    ) -> int | None:
        now = _utc_now_iso()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """
                SELECT project_id, status, worker_id, state_version, control_command,
                       control_version, control_request_id
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                self._conn.rollback()
                raise KeyError(f"job not found: {job_id}")
            if request_id is not None and row["control_request_id"] == request_id:
                if str(row["control_command"]) != command:
                    self._conn.rollback()
                    raise ValueError("request_id was already used for another control command")
                version = int(row["control_version"])
                self._conn.commit()
                return version
            if expected_status is not None and str(row["status"]) != expected_status:
                self._conn.commit()
                return None
            if (
                expected_state_version is not None
                and int(row["state_version"]) != expected_state_version
            ):
                self._conn.commit()
                return None
            version = int(row["control_version"]) + 1
            finalize_cancel = (
                finalize_cancel_if_unowned
                and command == "cancel"
                and row["worker_id"] is None
                and str(row["status"]) in {"queued", "running", "paused", "interrupted"}
            )
            self._conn.execute(
                """
                UPDATE jobs
                SET
                  control_command = ?,
                  control_version = ?,
                  control_ack_version = CASE WHEN ? THEN ? ELSE control_ack_version END,
                  control_requested_at = ?,
                  control_acknowledged_at = CASE WHEN ? THEN ? ELSE NULL END,
                  control_request_id = ?,
                  status = CASE WHEN ? THEN 'cancelled' ELSE status END,
                  state_version = state_version + 1,
                  updated_at = ?
                WHERE job_id = ?
                """,
                (
                    command,
                    version,
                    finalize_cancel,
                    version,
                    now,
                    finalize_cancel,
                    now,
                    request_id,
                    finalize_cancel,
                    now,
                    job_id,
                ),
            )
            if finalize_cancel:
                self._refresh_project_status_in_transaction(str(row["project_id"]), now)
            self._conn.commit()
            return version
        except Exception:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    def acknowledge_job_control(
        self, job_id: str, worker_id: str, control_version: int
    ) -> bool:
        now = _utc_now_iso()
        cursor = self._conn.execute(
            """
            UPDATE jobs
            SET control_ack_version = ?, control_acknowledged_at = ?, updated_at = ?
            WHERE job_id = ?
              AND worker_id = ?
              AND control_version = ?
              AND control_ack_version < ?
            """,
            (control_version, now, now, job_id, worker_id, control_version, control_version),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def acknowledge_unowned_job_control(self, job_id: str, control_version: int) -> bool:
        now = _utc_now_iso()
        cursor = self._conn.execute(
            """
            UPDATE jobs
            SET control_ack_version = ?, control_acknowledged_at = ?, updated_at = ?
            WHERE job_id = ?
              AND worker_id IS NULL
              AND control_version = ?
              AND control_ack_version < ?
            """,
            (control_version, now, now, job_id, control_version, control_version),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def append_job_event(self, channel: str, event: InfraEvent) -> int:
        ts = event.ts or _utc_now_iso()
        state_version = event.state_version
        if state_version is None:
            state_row = self._conn.execute(
                "SELECT state_version FROM jobs WHERE job_id = ?", (event.job_id,)
            ).fetchone()
            state_version = int(state_row["state_version"]) if state_row is not None else 0
        cursor = self._conn.execute(
            """
            INSERT INTO job_events (
              channel, event_type, project_id, job_id, payload_json, ts, state_version, request_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                event.event_type,
                event.project_id,
                event.job_id,
                json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
                ts,
                state_version,
                event.request_id,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an event cursor")
        return int(cursor.lastrowid)

    def list_job_events(
        self, channel: str, *, after_event_id: int = 0, limit: int = 1000
    ) -> list[InfraEvent]:
        safe_limit = max(1, min(limit, 10_000))
        rows = self._conn.execute(
            """
            SELECT
              event_id,
              event_type,
              project_id,
              job_id,
              payload_json,
              ts,
              state_version,
              request_id
            FROM job_events
            WHERE channel = ? AND event_id > ?
            ORDER BY event_id ASC
            LIMIT ?
            """,
            (channel, after_event_id, safe_limit),
        ).fetchall()
        return [
            InfraEvent(
                event_type=str(row["event_type"]),
                project_id=str(row["project_id"]),
                job_id=str(row["job_id"]),
                payload=dict(json.loads(str(row["payload_json"]))),
                ts=str(row["ts"]),
                event_id=int(row["event_id"]),
                state_version=int(row["state_version"]),
                request_id=row["request_id"],
            )
            for row in rows
        ]

    def latest_job_event_id(self, channel: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(event_id), 0) AS event_id FROM job_events WHERE channel = ?",
            (channel,),
        ).fetchone()
        return int(row["event_id"]) if row is not None else 0

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

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT value_json
            FROM system_settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value_json"])

    def set_setting(self, key: str, value_json: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO system_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
              value_json = excluded.value_json,
              updated_at = excluded.updated_at
            """,
            (key, value_json, now),
        )
        self._conn.commit()

    def get_auth_user(self) -> AuthUserRecord | None:
        row = self._conn.execute(
            """
            SELECT id, username, password_hash, created_at, updated_at
            FROM auth_user
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return AuthUserRecord(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_auth_user(self, *, user_id: str, username: str, password_hash: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO auth_user (id, username, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, now, now),
        )
        self._conn.commit()

    def update_auth_user_password_hash(self, *, user_id: str, password_hash: str) -> None:
        self._conn.execute(
            """
            UPDATE auth_user
            SET password_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (password_hash, _utc_now_iso(), user_id),
        )
        self._conn.commit()

    def append_operation_log(
        self,
        *,
        log_id: str,
        actor_type: str,
        actor_id: str | None,
        action: str,
        status: str,
        reason_code: str | None,
        created_at: str | None = None,
        meta_json: str = "{}",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO operation_logs (
              id,
              actor_type,
              actor_id,
              action,
              status,
              reason_code,
              created_at,
              meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                actor_type,
                actor_id,
                action,
                status,
                reason_code,
                created_at if created_at is not None else _utc_now_iso(),
                meta_json,
            ),
        )
        self._conn.commit()

    def list_recent_operation_logs(self, limit: int = 100) -> list[OperationLogRecord]:
        rows = self._conn.execute(
            """
            SELECT
              id,
              actor_type,
              actor_id,
              action,
              status,
              reason_code,
              created_at,
              meta_json
            FROM operation_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            OperationLogRecord(
                id=row["id"],
                actor_type=row["actor_type"],
                actor_id=row["actor_id"],
                action=row["action"],
                status=row["status"],
                reason_code=row["reason_code"],
                created_at=row["created_at"],
                meta_json=row["meta_json"],
            )
            for row in rows
        ]

    def get_next_allowed_at(self) -> str | None:
        row = self._conn.execute(
            """
            SELECT next_allowed_at
            FROM guest_cooldown
            WHERE key = ?
            """,
            (GLOBAL_GUEST_COOLDOWN_KEY,),
        ).fetchone()
        if row is None:
            return None
        return str(row["next_allowed_at"])

    def try_acquire(self, now: datetime, cooldown_seconds: int) -> bool:
        now_utc = now.astimezone(UTC)
        now_iso = now_utc.isoformat()
        next_allowed = now_utc.timestamp() + cooldown_seconds
        next_allowed_iso = datetime.fromtimestamp(next_allowed, UTC).isoformat()

        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """
                SELECT next_allowed_at
                FROM guest_cooldown
                WHERE key = ?
                """,
                (GLOBAL_GUEST_COOLDOWN_KEY,),
            ).fetchone()

            can_acquire = row is None or parse_iso8601(str(row["next_allowed_at"])) <= now_utc
            if can_acquire:
                self._conn.execute(
                    """
                    INSERT INTO guest_cooldown (key, next_allowed_at, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key)
                    DO UPDATE SET
                      next_allowed_at = excluded.next_allowed_at,
                      updated_at = excluded.updated_at
                    """,
                    (GLOBAL_GUEST_COOLDOWN_KEY, next_allowed_iso, now_iso),
                )
            self._conn.commit()
            return can_acquire
        except Exception:
            self._conn.rollback()
            raise

    def _to_job_record(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=str(row["job_id"]),
            project_id=str(row["project_id"]),
            status=str(row["status"]),
            stage=row["stage"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            delete_pending=bool(row["delete_pending"]),
            worker_id=row["worker_id"],
            attempt=int(row["attempt"]),
            claimed_at=row["claimed_at"],
            heartbeat_at=row["heartbeat_at"],
            control_command=row["control_command"],
            control_version=int(row["control_version"]),
            control_ack_version=int(row["control_ack_version"]),
            control_requested_at=row["control_requested_at"],
            control_acknowledged_at=row["control_acknowledged_at"],
            control_request_id=row["control_request_id"],
            state_version=int(row["state_version"]),
            progress=float(row["progress"]),
        )

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
