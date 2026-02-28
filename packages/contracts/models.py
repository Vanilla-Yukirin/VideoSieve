"""Canonical data contracts for cross-module communication."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class SourceType(StrEnum):
    """Supported project source kinds."""

    BILIBILI_URL = "bilibili_url"
    LOCAL_FILE = "local_file"


class ProjectStatus(StrEnum):
    """Project-level lifecycle status."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    """Job-level lifecycle status for one run."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageName(StrEnum):
    """Known stage identifiers."""

    INGEST = "ingest"
    HOTWORDS = "hotwords"
    ASR = "asr"
    KEYFRAMES = "keyframes"
    FRAME_SUMMARY = "frame_summary"
    FUSION = "fusion"
    DELIVERABLES = "deliverables"
    EXPORT = "export"


class StageStatus(StrEnum):
    """State for each pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(StrEnum):
    """Event stream types pushed to clients."""

    LOG = "log"
    PROGRESS = "progress"
    STAGE_CHANGED = "stage_changed"
    ARTIFACT_READY = "artifact_ready"
    ERROR = "error"
    CONTROL_ACK = "control_ack"


class ControlCommandType(StrEnum):
    """Client-issued control commands."""

    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    DELETE = "delete"


class ContractBase(BaseModel):
    """Base contract with strict shape and schema version."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default=SCHEMA_VERSION)


class Project(ContractBase):
    """Long-lived project container (distinct from a job run)."""

    project_id: str
    source_type: SourceType
    source_ref: str
    title: str
    status: ProjectStatus = ProjectStatus.QUEUED
    created_at: datetime


class Job(ContractBase):
    """Single execution run bound to exactly one project."""

    job_id: str
    project_id: str
    config_snapshot_path: str
    status: JobStatus = JobStatus.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StageState(ContractBase):
    """State snapshot for one stage within one job."""

    project_id: str
    job_id: str
    stage: StageName
    status: StageStatus = StageStatus.PENDING
    pct: float = Field(default=0.0, ge=0.0, le=100.0)
    updated_at: datetime


class EventEnvelope(ContractBase):
    """Generic event envelope for worker->gateway->web streams."""

    event_type: EventType
    project_id: str
    job_id: str
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ControlCommand(ContractBase):
    """Job-scoped control command from client to backend."""

    command: ControlCommandType
    project_id: str
    job_id: str
    issued_at: datetime
