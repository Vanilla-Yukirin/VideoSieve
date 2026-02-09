"""Typed models for ingest input layer providers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.models import SCHEMA_VERSION, SourceType


class IngestAssetSelection(BaseModel):
    """One asset quality selection via format ids only."""

    model_config = ConfigDict(extra="forbid")

    video_format_id: str
    audio_format_id: str | None = None


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
    cookie_id: str | None = None
    cookie_secret_ref: str | None = None
    cookie_content: str | None = None
    cookie_file_path: str | None = None
    ytdlp_sort: str | None = None

    # Backward-compatible single-asset selector.
    video_format_id: str | None = None
    audio_format_id: str | None = None

    # Preferred dual-asset selector.
    analysis_asset: IngestAssetSelection | None = None
    quality_asset: IngestAssetSelection | None = None

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

        if self.audio_format_id and not self.video_format_id:
            raise ValueError("audio_format_id requires video_format_id")
        if self.analysis_asset and not self.analysis_asset.video_format_id:
            raise ValueError("analysis_asset.video_format_id is required")
        if self.quality_asset and not self.quality_asset.video_format_id:
            raise ValueError("quality_asset.video_format_id is required")
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
    selected_format: str | None = None
    selected_video_format_id: str | None = None
    selected_audio_format_id: str | None = None
    analysis_selected_video_format_id: str | None = None
    analysis_selected_audio_format_id: str | None = None
    quality_selected_video_format_id: str | None = None
    quality_selected_audio_format_id: str | None = None
    dedupe_applied: bool = False
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


class IngestFormatOption(BaseModel):
    """One candidate media format from yt-dlp probe."""

    model_config = ConfigDict(extra="forbid")

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


class IngestFormatProbeResult(BaseModel):
    """Probe result for one URL with available format candidates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source_url: str
    title: str
    uploader: str | None = None
    duration_seconds: float | None = None
    webpage_url: str | None = None
    formats: list[IngestFormatOption] = Field(default_factory=list)
