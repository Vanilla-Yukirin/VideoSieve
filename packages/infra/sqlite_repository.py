"""SQLite-backed minimal implementation of JobRepository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import JobRepository
from .models import (
    AuthUserRecord,
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

    def delete_project(self, project_id: str) -> None:
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
