"""Ingest provider implementations for local files and URL downloads."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from infra import WorkspaceStore

from .errors import (
    INGEST_DEPENDENCY_MISSING,
    INGEST_INVALID_SOURCE,
    INGEST_SOURCE_NOT_FOUND,
    IngestError,
    map_download_error,
)
from .models import IngestRequest


class IngestProvider(Protocol):
    """Provider interface for resolving source media to workspace media/source.mp4."""

    def materialize_source(
        self,
        workspace: WorkspaceStore,
        request: IngestRequest,
    ) -> tuple[Path, dict[str, Any], int]:
        """Write source video into workspace and return metadata + retry count."""
        ...


def _normalize_local_source(source_path: str) -> Path:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise IngestError(
            code=INGEST_SOURCE_NOT_FOUND,
            message=f"local source file not found: {source}",
            retryable=False,
            context={"stage": "ingest"},
        )
    if not source.is_file():
        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message=f"local source must be a file path: {source}",
            retryable=False,
            context={"stage": "ingest"},
        )
    return source


class LocalFileIngestProvider:
    """Local-path import provider."""

    def materialize_source(
        self,
        workspace: WorkspaceStore,
        request: IngestRequest,
    ) -> tuple[Path, dict[str, Any], int]:
        if not request.source_path:
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message="source_path is required for local ingest",
                retryable=False,
                context={"stage": "ingest"},
            )

        source = _normalize_local_source(request.source_path)
        workspace.ensure_project_layout(request.project_id)
        target_video = workspace.source_video_file(request.project_id)
        shutil.copy2(source, target_video)

        metadata = {
            "source_ref": str(source),
            "title": request.title or source.stem,
            "description": request.description,
            "tags": request.tags,
            "language_hint": request.language_hint,
        }
        return target_video, metadata, 0


def _load_yt_dlp() -> tuple[ModuleType, type[Exception]]:
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError

        return yt_dlp, DownloadError
    except Exception as exc:  # pragma: no cover - exercised in runtime envs
        raise IngestError(
            code=INGEST_DEPENDENCY_MISSING,
            message=f"yt-dlp is not available: {exc}",
            hint="Install dependency `yt-dlp` and retry URL ingest.",
            retryable=False,
            context={"stage": "ingest"},
        ) from exc


@contextmanager
def _cookie_file_for_request(request: IngestRequest) -> Iterator[str | None]:
    if request.cookie_content:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".cookies.txt", delete=False, encoding="utf-8"
        )
        try:
            tmp.write(request.cookie_content)
            tmp.flush()
            tmp.close()
            yield tmp.name
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        return

    if request.cookie_file_path:
        cookie_path = Path(request.cookie_file_path).expanduser().resolve()
        if not cookie_path.exists() or not cookie_path.is_file():
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message=f"cookie_file_path is invalid: {cookie_path}",
                retryable=False,
                context={"stage": "ingest"},
            )
        yield str(cookie_path)
        return

    yield None


class YtDlpIngestProvider:
    """URL ingest provider backed by yt-dlp."""

    def materialize_source(
        self,
        workspace: WorkspaceStore,
        request: IngestRequest,
    ) -> tuple[Path, dict[str, Any], int]:
        if not request.source_url:
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message="source_url is required for URL ingest",
                retryable=False,
                context={"stage": "ingest"},
            )

        workspace.ensure_project_layout(request.project_id)
        target_video = workspace.source_video_file(request.project_id)
        attempts = request.download_retries + 1
        last_error: IngestError | None = None

        with _cookie_file_for_request(request) as cookie_file:
            for attempt in range(1, attempts + 1):
                try:
                    info = self._download_once(
                        source_url=request.source_url,
                        target_video=target_video,
                        cookie_file=cookie_file,
                        project_id=request.project_id,
                        job_id=request.job_id,
                    )
                    metadata = {
                        "source_ref": request.source_url,
                        "title": request.title or str(info.get("title") or "untitled"),
                        "description": request.description or str(info.get("description") or ""),
                        "tags": request.tags or [str(item) for item in (info.get("tags") or [])],
                        "language_hint": request.language_hint,
                        "uploader": str(info.get("uploader")) if info.get("uploader") else None,
                        "duration_seconds": float(info["duration"])
                        if info.get("duration")
                        else None,
                        "webpage_url": str(info.get("webpage_url") or request.source_url),
                    }
                    return target_video, metadata, attempt - 1
                except IngestError as exc:
                    last_error = exc
                    if not exc.retryable or attempt >= attempts:
                        raise

        if last_error is not None:
            raise last_error

        raise IngestError(
            code=INGEST_INVALID_SOURCE,
            message="unreachable URL ingest state",
            retryable=False,
            context={"stage": "ingest"},
        )

    def _download_once(
        self,
        *,
        source_url: str,
        target_video: Path,
        cookie_file: str | None,
        project_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        yt_dlp, download_error_type = _load_yt_dlp()
        ydl_opts: dict[str, Any] = {
            "outtmpl": str(target_video),
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 0,
            "merge_output_format": "mp4",
        }
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=True)
        except download_error_type as exc:
            raise map_download_error(
                str(exc),
                project_id=project_id,
                job_id=job_id,
                retryable=True,
            ) from exc

        if not target_video.exists():
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message=f"download completed but target video missing: {target_video}",
                retryable=True,
                context={"stage": "ingest"},
            )
        return info if isinstance(info, dict) else {}
