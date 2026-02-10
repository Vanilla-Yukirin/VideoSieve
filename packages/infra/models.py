"""Typed records and event payloads for infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass(slots=True)
class UserCookieRecord:
    """Encrypted cookie vault record scoped to one user."""

    id: str
    user_id: str
    name: str
    cookie_encrypted: str
    is_default: bool
    status: str
    last_validated_at: str | None
    last_error_code: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SystemSettingRecord:
    """Runtime-configurable setting persisted in SQLite."""

    key: str
    value_json: str
    updated_at: str


@dataclass(slots=True)
class AuthUserRecord:
    """Single-user auth identity row."""

    id: str
    username: str
    password_hash: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class OperationLogRecord:
    """Operation audit/event log row."""

    id: str
    actor_type: str
    actor_id: str | None
    action: str
    status: str
    reason_code: str | None
    created_at: str
    meta_json: str


@dataclass(slots=True)
class GuestCooldownRecord:
    """Server-wide cooldown state for guest submissions."""

    key: str
    next_allowed_at: str
    updated_at: str


def parse_iso8601(value: str) -> datetime:
    """Parse ISO8601 timestamps supporting trailing Z."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))
