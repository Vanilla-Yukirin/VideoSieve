"""Typed models for ingest local-file MVP."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts.models import SCHEMA_VERSION, SourceType


class IngestRequest(BaseModel):
    """Input payload for local file ingest."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    job_id: str
    source_path: str
    title: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    language_hint: str | None = None


class IngestMeta(BaseModel):
    """Canonical `meta/meta.json` payload produced by ingest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    project_id: str
    job_id: str
    source_type: SourceType = SourceType.LOCAL_FILE
    source_ref: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    language_hint: str | None = None
    ingested_at: datetime


class IngestResult(BaseModel):
    """Result payload containing written artifact paths."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    job_id: str
    source_video_path: str
    meta_path: str
    meta: IngestMeta
