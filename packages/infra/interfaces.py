"""Abstract interfaces for infra adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from .models import InfraEvent, JobRecord, ProjectRecord

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
