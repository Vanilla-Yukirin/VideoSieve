"""Request/response models for the API control plane."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts import ControlCommandType


class ApiModel(BaseModel):
    """Base API model with strict field handling."""

    model_config = ConfigDict(extra="forbid")


class ProjectCreateRequest(ApiModel):
    """Project create payload."""

    title: str | None = None


class JobCreateRequest(ApiModel):
    """Job create payload."""

    project_id: str


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
