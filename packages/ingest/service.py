"""Ingest service entrypoints for local and URL sources."""

from __future__ import annotations

from datetime import UTC, datetime

from contracts import SourceType
from infra import WorkspaceStore

from .errors import INGEST_INVALID_SOURCE, IngestError
from .models import IngestFormatProbeResult, IngestMeta, IngestRequest, IngestResult
from .providers import IngestProvider, LocalFileIngestProvider, YtDlpIngestProvider


def _write_meta(
    workspace: WorkspaceStore,
    request: IngestRequest,
    *,
    source_ref: str,
    title: str,
    description: str,
    tags: list[str],
    language_hint: str | None,
    source_type: SourceType,
    uploader: str | None = None,
    duration_seconds: float | None = None,
    webpage_url: str | None = None,
    selected_format: str | None = None,
    selected_video_format_id: str | None = None,
    selected_audio_format_id: str | None = None,
) -> IngestMeta:
    target_meta = workspace.meta_file(request.project_id)
    meta = IngestMeta(
        project_id=request.project_id,
        job_id=request.job_id,
        source_type=source_type,
        source_ref=source_ref,
        title=title,
        description=description,
        tags=tags,
        language_hint=language_hint,
        uploader=uploader,
        duration_seconds=duration_seconds,
        webpage_url=webpage_url,
        selected_format=selected_format,
        selected_video_format_id=selected_video_format_id,
        selected_audio_format_id=selected_audio_format_id,
        ingested_at=datetime.now(UTC),
    )
    target_meta.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta


def run_local_ingest(workspace: WorkspaceStore, request: IngestRequest) -> IngestResult:
    """Copy local media into workspace and emit `meta/meta.json`."""

    if not request.source_path:
        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message="source_path is required for run_local_ingest",
            retryable=False,
            context={"project_id": request.project_id, "job_id": request.job_id, "stage": "ingest"},
        )
    provider = LocalFileIngestProvider()
    target_video, metadata, retry_count = provider.materialize_source(workspace, request)
    meta = _write_meta(
        workspace,
        request,
        source_ref=metadata["source_ref"],
        title=metadata["title"],
        description=metadata.get("description", ""),
        tags=metadata.get("tags", []),
        language_hint=metadata.get("language_hint"),
        source_type=SourceType.LOCAL_FILE,
    )

    return IngestResult(
        project_id=request.project_id,
        job_id=request.job_id,
        source_video_path=str(target_video),
        meta_path=str(workspace.meta_file(request.project_id)),
        meta=meta,
        retry_count=retry_count,
    )


def run_ingest(workspace: WorkspaceStore, request: IngestRequest) -> IngestResult:
    """Run ingest by selecting local-file or URL provider."""

    provider: IngestProvider
    if request.source_path:
        provider = LocalFileIngestProvider()
        source_type = SourceType.LOCAL_FILE
    elif request.source_url:
        provider = YtDlpIngestProvider()
        source_type = SourceType.BILIBILI_URL
    else:
        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message="request must include source_path or source_url",
            retryable=False,
            context={"project_id": request.project_id, "job_id": request.job_id, "stage": "ingest"},
        )

    target_video, metadata, retry_count = provider.materialize_source(workspace, request)
    meta = _write_meta(
        workspace,
        request,
        source_ref=metadata["source_ref"],
        title=metadata["title"],
        description=metadata.get("description", ""),
        tags=metadata.get("tags", []),
        language_hint=metadata.get("language_hint"),
        source_type=source_type,
        uploader=metadata.get("uploader"),
        duration_seconds=metadata.get("duration_seconds"),
        webpage_url=metadata.get("webpage_url"),
        selected_format=metadata.get("selected_format"),
        selected_video_format_id=metadata.get("selected_video_format_id"),
        selected_audio_format_id=metadata.get("selected_audio_format_id"),
    )
    return IngestResult(
        project_id=request.project_id,
        job_id=request.job_id,
        source_video_path=str(target_video),
        meta_path=str(workspace.meta_file(request.project_id)),
        meta=meta,
        retry_count=retry_count,
    )


def run_url_ingest(workspace: WorkspaceStore, request: IngestRequest) -> IngestResult:
    """URL-specific helper entrypoint backed by yt-dlp provider."""

    if not request.source_url:
        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message="source_url is required for run_url_ingest",
            retryable=False,
            context={"project_id": request.project_id, "job_id": request.job_id, "stage": "ingest"},
        )
    return run_ingest(workspace, request)


def probe_url_formats(request: IngestRequest) -> IngestFormatProbeResult:
    """Probe one URL and return selectable format options without downloading."""
    if not request.source_url:
        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message="source_url is required for probe_url_formats",
            retryable=False,
            context={"project_id": request.project_id, "job_id": request.job_id, "stage": "ingest"},
        )
    provider = YtDlpIngestProvider()
    return provider.probe_formats(request)
