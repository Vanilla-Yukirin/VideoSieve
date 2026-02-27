"""Abstract interfaces for infra adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .models import (
    AuthUserRecord,
    InfraEvent,
    JobRecord,
    OperationLogRecord,
    ProjectRecord,
    UserCookieRecord,
)

EventHandler = Callable[[InfraEvent], None]


class EventSubscription(ABC):
    """Subscription handle returned by the event bus."""

    @abstractmethod
    def unsubscribe(self) -> None:
        """Unregister the underlying subscription."""


class EventBus(ABC):
    """Publisher/subscriber abstraction for infra event transports."""

    @abstractmethod
    def publish(self, channel: str, event: InfraEvent) -> None:
        """Publish one event envelope to a channel."""

    @abstractmethod
    def subscribe(self, channel: str, handler: EventHandler) -> EventSubscription:
        """Subscribe to one channel and return an unsubscribe handle."""

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""


class JobRepository(ABC):
    """Persistent project/job metadata storage."""

    @abstractmethod
    def ensure_schema(self) -> None:
        """Create or migrate the minimal required schema."""

    @abstractmethod
    def upsert_project(self, project_id: str, *, title: str | None, status: str) -> None:
        """Insert or update one project row."""

    @abstractmethod
    def get_project(self, project_id: str) -> ProjectRecord | None:
        """Fetch one project row by id."""

    @abstractmethod
    def update_project_status(self, project_id: str, status: str) -> None:
        """Update project status."""

    @abstractmethod
    def create_job(
        self, job_id: str, project_id: str, *, status: str, stage: str | None = None
    ) -> None:
        """Insert one job row."""

    @abstractmethod
    def get_job(self, job_id: str) -> JobRecord | None:
        """Fetch one job row by id."""

    @abstractmethod
    def list_jobs_for_project(self, project_id: str) -> list[JobRecord]:
        """List jobs for one project ordered by creation time."""

    @abstractmethod
    def update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        stage: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update job status and optional stage/error fields."""

    @abstractmethod
    def close(self) -> None:
        """Release underlying connection resources."""

    @abstractmethod
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
        """Create one encrypted cookie row."""

    @abstractmethod
    def list_user_cookies(self, user_id: str) -> list[UserCookieRecord]:
        """List all cookie rows for one user."""

    @abstractmethod
    def get_user_cookie(self, cookie_id: str, user_id: str) -> UserCookieRecord | None:
        """Get one cookie row by id scoped to user."""

    @abstractmethod
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
        """Update one cookie row fields."""

    @abstractmethod
    def delete_user_cookie(self, cookie_id: str, user_id: str) -> None:
        """Delete one cookie row scoped to user."""

    @abstractmethod
    def clear_default_cookie_for_user(self, user_id: str) -> None:
        """Clear default flag for all cookies of one user."""

    @abstractmethod
    def get_setting(self, key: str) -> str | None:
        """Read one setting value_json by key."""

    @abstractmethod
    def set_setting(self, key: str, value_json: str) -> None:
        """Upsert one setting value_json by key."""

    @abstractmethod
    def get_auth_user(self) -> AuthUserRecord | None:
        """Read the single auth user record if present."""

    @abstractmethod
    def create_auth_user(self, *, user_id: str, username: str, password_hash: str) -> None:
        """Create the single auth user record."""

    @abstractmethod
    def update_auth_user_password_hash(self, *, user_id: str, password_hash: str) -> None:
        """Update password hash for one auth user by id."""

    @abstractmethod
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
        """Append one operation log entry."""

    @abstractmethod
    def list_recent_operation_logs(self, limit: int = 100) -> list[OperationLogRecord]:
        """List operation logs ordered by newest first."""

    @abstractmethod
    def get_next_allowed_at(self) -> str | None:
        """Read server-wide guest cooldown next_allowed_at."""

    @abstractmethod
    def try_acquire(self, now: datetime, cooldown_seconds: int) -> bool:
        """Try to acquire cooldown slot atomically; return True when accepted."""


class WorkspaceStore(ABC):
    """Workspace path and layout helper."""

    @abstractmethod
    def project_root(self, project_id: str) -> Path:
        """Return canonical root path for one project workspace."""

    @abstractmethod
    def ensure_project_layout(self, project_id: str) -> Path:
        """Create canonical workspace directory layout if missing."""

    @abstractmethod
    def path(self, project_id: str, *parts: str) -> Path:
        """Build one safe path under the project workspace root."""

    @abstractmethod
    def job_root(self, project_id: str, job_id: str) -> Path:
        """Return canonical root path for one job workspace."""

    @abstractmethod
    def ensure_job_layout(self, project_id: str, job_id: str) -> Path:
        """Create canonical job workspace directory layout if missing."""

    @abstractmethod
    def job_path(self, project_id: str, job_id: str, *parts: str) -> Path:
        """Build one safe path under the job workspace root."""

    @abstractmethod
    def meta_file(self, project_id: str) -> Path:
        """Return `meta/meta.json` path for one project."""

    @abstractmethod
    def job_meta_file(self, project_id: str, job_id: str) -> Path:
        """Return `meta/meta.json` path for one job."""

    @abstractmethod
    def config_snapshot_file(self, project_id: str, job_id: str) -> Path:
        """Return `meta/config.snapshot.json` path for one job."""

    @abstractmethod
    def source_video_file(self, project_id: str, job_id: str) -> Path:
        """Return `media/source.mp4` path for one job."""

    @abstractmethod
    def audio_file(self, project_id: str, job_id: str) -> Path:
        """Return `media/audio.wav` path for one job."""

    @abstractmethod
    def hotwords_file(self, project_id: str, job_id: str) -> Path:
        """Return `hotwords/hotwords.json` path for one job."""

    @abstractmethod
    def transcript_file(self, project_id: str, job_id: str) -> Path:
        """Return `asr/transcript.jsonl` path for one job."""

    @abstractmethod
    def keyframes_file(self, project_id: str, job_id: str) -> Path:
        """Return `frames/keyframes.jsonl` path for one job."""

    @abstractmethod
    def frame_summary_file(self, project_id: str, job_id: str) -> Path:
        """Return `frame_summary/frame_summary.jsonl` path for one job."""

    @abstractmethod
    def timeline_file(self, project_id: str, job_id: str) -> Path:
        """Return `fusion/timeline.json` path for one job."""

    @abstractmethod
    def clean_transcript_file(self, project_id: str, job_id: str) -> Path:
        """Return `outputs/clean_transcript.md` path for one job."""

    @abstractmethod
    def illustrated_notes_file(self, project_id: str, job_id: str) -> Path:
        """Return `outputs/illustrated_notes.md` path for one job."""

    @abstractmethod
    def summary_file(self, project_id: str, job_id: str) -> Path:
        """Return `outputs/summary.json` path for one job."""

    @abstractmethod
    def worker_log_file(self, project_id: str, job_id: str) -> Path:
        """Return `logs/worker.log` path for one job."""
