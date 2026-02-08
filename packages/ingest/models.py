"""Typed models for ingest input layer providers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.models import SCHEMA_VERSION, SourceType


class IngestRequest(BaseModel):
    """Input payload for local import or URL download ingest."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    job_id: str
    source_type: SourceType = SourceType.LOCAL_FILE
    source_path: str | None = None
    source_url: str | None = None
    title: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    language_hint: str | None = None
    download_retries: int = Field(default=2, ge=0, le=5)
    cookie_content: str | None = None
    cookie_file_path: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> IngestRequest:
        has_path = bool(self.source_path)
        has_url = bool(self.source_url)
        if has_path == has_url:
            raise ValueError("exactly one of source_path/source_url is required")
        if has_path:
            self.source_type = SourceType.LOCAL_FILE
        else:
            self.source_type = SourceType.BILIBILI_URL
        return self


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
    uploader: str | None = None
    duration_seconds: float | None = None
    webpage_url: str | None = None
    ingested_at: datetime


class IngestResult(BaseModel):
    """Result payload containing written artifact paths."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    job_id: str
    source_video_path: str
    meta_path: str
    meta: IngestMeta
    retry_count: int = 0
