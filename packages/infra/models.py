"""Typed records and event payloads for infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InfraEvent:
    """Event envelope shared by event bus publishers/subscribers."""

    event_type: str
    project_id: str
    job_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str | None = None


@dataclass(slots=True)
class ProjectRecord:
    """Minimal persistent project state."""

    project_id: str
    title: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class JobRecord:
    """Minimal persistent job state."""

    job_id: str
    project_id: str
    status: str
    stage: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
