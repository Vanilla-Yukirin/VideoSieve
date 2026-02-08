"""Request/response models for the API control plane."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts import ControlCommandType


class ApiModel(BaseModel):
    """Base API model with strict field handling."""

    model_config = ConfigDict(extra="forbid")


class IngestParams(ApiModel):
    """Parameters for job ingestion configuration."""

    source_url: str | None = None
    video_format_id: str | None = None
    audio_format_id: str | None = None
    ytdlp_format: str | None = None
    ytdlp_sort: str | None = None
    cookie_file_path: str | None = None
    cookie_secret_ref: str | None = None


class ProjectCreateRequest(ApiModel):
    """Project create payload."""

    title: str | None = None


class JobCreateRequest(ApiModel):
    """Job create payload."""

    project_id: str
    ingest: IngestParams | None = None


class IngestProbeRequest(ApiModel):
    """Probe payload for URL format options."""

    source_url: str
    cookie_file_path: str | None = None
    ytdlp_sort: str | None = None


class IngestFormatItem(ApiModel):
    """One selectable format option for frontend quality picker."""

    format_id: str
    ext: str | None = None
    resolution: str | None = None
    fps: float | None = None
    tbr: float | None = None
    protocol: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize_approx: int | None = None
    is_video_only: bool = False
    is_audio_only: bool = False


class IngestProbeResponse(ApiModel):
    """Probe response consumed by web quality selection UI."""

    source_url: str
    title: str
    uploader: str | None = None
    duration_seconds: float | None = None
    webpage_url: str | None = None
    formats: list[IngestFormatItem] = Field(default_factory=list)


class ArtifactItem(ApiModel):
    """Workspace artifact descriptor."""

    path: str
    size_bytes: int = Field(ge=0)


class JobSnapshot(ApiModel):
    """HTTP snapshot as source-of-truth for UI state convergence."""

    project_id: str
    job_id: str
    status: str
    current_stage: str | None = None
    progress: float = Field(ge=0.0, le=100.0)
    latest_logs: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactItem] = Field(default_factory=list)


class WsControlCommand(ApiModel):
    """WS client command payload."""

    command: ControlCommandType
