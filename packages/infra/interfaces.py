"""Abstract interfaces for infra adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .models import (
    InfraEvent,
    JobRecord,
    OperationLogRecord,
    ProjectRecord,
    ProviderSecretRecord,
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
    def subscribe(
        self,
        channel: str,
        handler: EventHandler,
        *,
        after_cursor: int | None = None,
    ) -> EventSubscription:
        """Subscribe to one channel and return an unsubscribe handle."""

    @abstractmethod
    def list_after(
        self, channel: str, *, after_cursor: int, limit: int = 1000
    ) -> list[InfraEvent]:
        """Replay events after one monotonic cursor."""

    @abstractmethod
    def latest_cursor(self, channel: str) -> int:
        """Return the latest cursor for one channel, or zero."""

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
    def list_projects(self) -> list[ProjectRecord]:
        """List projects in stable newest-first creation order."""

    @abstractmethod
    def update_project_status(self, project_id: str, status: str) -> None:
        """Update project status."""

    @abstractmethod
    def refresh_project_status(self, project_id: str) -> str | None:
        """Derive and persist project status from all of its jobs."""

    @abstractmethod
    def delete_project(self, project_id: str) -> None:
        """Delete one project and all its jobs."""

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
        expected_worker_id: str | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        """Update job state, optionally fenced to one worker attempt."""

    @abstractmethod
    def update_job_progress(
        self,
        job_id: str,
        *,
        progress: float,
        stage: str | None,
        expected_worker_id: str | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        """Persist progress, optionally fenced to one worker attempt."""

    @abstractmethod
    def delete_job(self, job_id: str) -> None:
        """Delete one job row by id."""

    @abstractmethod
    def set_job_delete_pending(self, job_id: str, pending: bool) -> None:
        """Persist delete-intent flag for one job."""

    @abstractmethod
    def list_pending_delete_job_ids(self) -> list[str]:
        """List job ids that still have delete intent pending."""

    @abstractmethod
    def claim_next_job(self, worker_id: str) -> JobRecord | None:
        """Atomically claim the oldest runnable job for one worker."""

    @abstractmethod
    def heartbeat_job(
        self, job_id: str, worker_id: str, *, expected_attempt: int | None = None
    ) -> bool:
        """Refresh a job lease when it is still owned by the worker."""

    @abstractmethod
    def release_job_claim(
        self, job_id: str, worker_id: str, *, expected_attempt: int | None = None
    ) -> bool:
        """Clear a worker claim when it is still owned by that worker."""

    @abstractmethod
    def mark_stale_jobs_interrupted(self, stale_before: datetime) -> list[str]:
        """Mark stale claimed jobs interrupted without automatically rerunning them."""

    @abstractmethod
    def recover_interrupted_job(
        self,
        job_id: str,
        *,
        request_id: str | None = None,
        expected_state_version: int | None = None,
    ) -> bool:
        """Explicitly move an interrupted job back to the durable queue."""

    @abstractmethod
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
        """Persist an idempotent, optionally state-conditional control request."""

    @abstractmethod
    def acknowledge_job_control(
        self, job_id: str, worker_id: str, control_version: int
    ) -> bool:
        """Acknowledge one control version from the worker that owns the job."""

    @abstractmethod
    def acknowledge_unowned_job_control(self, job_id: str, control_version: int) -> bool:
        """Acknowledge a control version when no worker owns or executes the job."""

    @abstractmethod
    def append_job_event(self, channel: str, event: InfraEvent) -> int:
        """Persist one event and return its monotonic cursor."""

    @abstractmethod
    def list_job_events(
        self, channel: str, *, after_event_id: int = 0, limit: int = 1000
    ) -> list[InfraEvent]:
        """List persisted events after one cursor."""

    @abstractmethod
    def latest_job_event_id(self, channel: str) -> int:
        """Return the latest persisted cursor for one channel, or zero."""

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
    def create_provider_secret(
        self, *, secret_id: str, kind: str, secret_encrypted: str
    ) -> None:
        """Create and activate a new encrypted credential version."""

    @abstractmethod
    def get_active_provider_secret(self, kind: str) -> ProviderSecretRecord | None:
        """Return the active credential for one provider kind."""

    @abstractmethod
    def get_provider_secret(
        self, secret_id: str, *, expected_kind: str
    ) -> ProviderSecretRecord | None:
        """Resolve one credential version while enforcing its provider kind."""

    @abstractmethod
    def clear_active_provider_secret(self, kind: str) -> None:
        """Deactivate the current credential while preserving referenced versions."""

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
    def deliverables_manifest_file(self, project_id: str, job_id: str) -> Path:
        """Return the generation readiness manifest path for one job."""

    @abstractmethod
    def worker_log_file(self, project_id: str, job_id: str) -> Path:
        """Return `logs/worker.log` path for one job."""
