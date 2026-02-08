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
from .models import IngestFormatOption, IngestFormatProbeResult, IngestRequest


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


DEFAULT_FORMAT_SELECTOR = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[ext=mp4]/best"


def _build_format_selector(video_format_id: str | None, audio_format_id: str | None) -> str:
    if video_format_id and audio_format_id:
        return f"{video_format_id}+{audio_format_id}"
    if video_format_id:
        return video_format_id
    return DEFAULT_FORMAT_SELECTOR


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _to_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _to_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return str(value)


def _extract_format_options(info: dict[str, Any]) -> list[IngestFormatOption]:
    rows = info.get("formats")
    if not isinstance(rows, list):
        return []

    options: list[IngestFormatOption] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        format_id = _to_str(row.get("format_id"))
        if not format_id:
            continue

        vcodec = _to_str(row.get("vcodec"))
        acodec = _to_str(row.get("acodec"))
        is_video_only = bool(vcodec and vcodec != "none" and (not acodec or acodec == "none"))
        is_audio_only = bool(acodec and acodec != "none" and (not vcodec or vcodec == "none"))

        options.append(
            IngestFormatOption(
                format_id=format_id,
                ext=_to_str(row.get("ext")),
                resolution=_to_str(row.get("resolution")),
                fps=_to_float(row.get("fps")),
                tbr=_to_float(row.get("tbr")),
                protocol=_to_str(row.get("protocol")),
                vcodec=vcodec,
                acodec=acodec,
                filesize_approx=_to_int(row.get("filesize_approx") or row.get("filesize")),
                is_video_only=is_video_only,
                is_audio_only=is_audio_only,
            )
        )
    return options


def _extract_selected_format_ids(info: dict[str, Any]) -> tuple[str | None, str | None]:
    requested = info.get("requested_downloads")
    if not isinstance(requested, list):
        return None, None

    video_id: str | None = None
    audio_id: str | None = None
    for row in requested:
        if not isinstance(row, dict):
            continue
        format_id = _to_str(row.get("format_id"))
        vcodec = _to_str(row.get("vcodec"))
        acodec = _to_str(row.get("acodec"))
        if not format_id:
            continue
        if vcodec and vcodec != "none" and (not acodec or acodec == "none"):
            video_id = format_id
        elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            audio_id = format_id

    return video_id, audio_id


class YtDlpIngestProvider:
    """URL ingest provider backed by yt-dlp."""

    def probe_formats(self, request: IngestRequest) -> IngestFormatProbeResult:
        """Probe one URL and return selectable format options."""
        if not request.source_url:
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message="source_url is required for URL probe",
                retryable=False,
                context={"stage": "ingest"},
            )

        with _cookie_file_for_request(request) as cookie_file:
            selector = _build_format_selector(request.video_format_id, request.audio_format_id)
            info = self._extract_info(
                source_url=request.source_url,
                cookie_file=cookie_file,
                project_id=request.project_id,
                job_id=request.job_id,
                download=False,
                format_selector=selector,
                sort_rule=request.ytdlp_sort,
                target_video=None,
            )

        return IngestFormatProbeResult(
            source_url=request.source_url,
            title=str(info.get("title") or "untitled"),
            uploader=_to_str(info.get("uploader")),
            duration_seconds=_to_float(info.get("duration")),
            webpage_url=_to_str(info.get("webpage_url")) or request.source_url,
            formats=_extract_format_options(info),
        )

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
        analysis_video = workspace.path(request.project_id, "media", "source.analysis.mp4")
        analysis_pair, quality_pair = self._resolve_asset_pairs(request)
        dedupe_applied = analysis_pair == quality_pair

        plan: list[tuple[str, Path, tuple[str | None, str | None]]] = [
            ("quality", target_video, quality_pair)
        ]
        if not dedupe_applied:
            plan.append(("analysis", analysis_video, analysis_pair))
        elif analysis_video.exists():
            analysis_video.unlink()

        attempts = request.download_retries + 1
        last_error: IngestError | None = None

        with _cookie_file_for_request(request) as cookie_file:
            for attempt in range(1, attempts + 1):
                try:
                    info_by_role: dict[str, dict[str, Any]] = {}
                    for role, target_path, pair in plan:
                        info_by_role[role] = self._download_once(
                            request=request,
                            target_video=target_path,
                            cookie_file=cookie_file,
                            pair=pair,
                        )

                    quality_info = info_by_role["quality"]
                    analysis_info = info_by_role.get("analysis", quality_info)
                    quality_video_id, quality_audio_id = _extract_selected_format_ids(quality_info)
                    analysis_video_id, analysis_audio_id = _extract_selected_format_ids(
                        analysis_info
                    )
                    quality_selector = _build_format_selector(*quality_pair)
                    metadata = {
                        "source_ref": request.source_url,
                        "title": request.title or str(quality_info.get("title") or "untitled"),
                        "description": request.description
                        or str(quality_info.get("description") or ""),
                        "tags": request.tags
                        or [str(item) for item in (quality_info.get("tags") or [])],
                        "language_hint": request.language_hint,
                        "uploader": (
                            str(quality_info.get("uploader"))
                            if quality_info.get("uploader")
                            else None
                        ),
                        "duration_seconds": float(quality_info["duration"])
                        if quality_info.get("duration")
                        else None,
                        "webpage_url": str(quality_info.get("webpage_url") or request.source_url),
                        "selected_format": quality_selector,
                        "selected_video_format_id": quality_pair[0] or quality_video_id,
                        "selected_audio_format_id": quality_pair[1] or quality_audio_id,
                        "analysis_selected_video_format_id": analysis_pair[0] or analysis_video_id,
                        "analysis_selected_audio_format_id": analysis_pair[1] or analysis_audio_id,
                        "quality_selected_video_format_id": quality_pair[0] or quality_video_id,
                        "quality_selected_audio_format_id": quality_pair[1] or quality_audio_id,
                        "dedupe_applied": dedupe_applied,
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
        request: IngestRequest,
        target_video: Path,
        cookie_file: str | None,
        pair: tuple[str | None, str | None],
    ) -> dict[str, Any]:
        if target_video.exists():
            target_video.unlink()
        return self._extract_info(
            source_url=request.source_url or "",
            target_video=target_video,
            cookie_file=cookie_file,
            project_id=request.project_id,
            job_id=request.job_id,
            download=True,
            format_selector=_build_format_selector(pair[0], pair[1]),
            sort_rule=request.ytdlp_sort,
        )

    def _resolve_asset_pairs(
        self,
        request: IngestRequest,
    ) -> tuple[tuple[str | None, str | None], tuple[str | None, str | None]]:
        legacy_pair: tuple[str | None, str | None] = (
            request.video_format_id,
            request.audio_format_id,
        )

        analysis_pair: tuple[str | None, str | None] | None = (
            (
                request.analysis_asset.video_format_id,
                request.analysis_asset.audio_format_id,
            )
            if request.analysis_asset
            else None
        )
        quality_pair: tuple[str | None, str | None] | None = (
            (
                request.quality_asset.video_format_id,
                request.quality_asset.audio_format_id,
            )
            if request.quality_asset
            else None
        )

        if analysis_pair is None and quality_pair is None:
            return legacy_pair, legacy_pair
        if analysis_pair is None:
            assert quality_pair is not None
            return quality_pair, quality_pair
        if quality_pair is None:
            assert analysis_pair is not None
            return analysis_pair, analysis_pair
        return analysis_pair, quality_pair

    def _extract_info(
        self,
        *,
        source_url: str,
        cookie_file: str | None,
        project_id: str,
        job_id: str,
        download: bool,
        format_selector: str,
        sort_rule: str | None,
        target_video: Path | None,
    ) -> dict[str, Any]:
        yt_dlp, download_error_type = _load_yt_dlp()
        ydl_opts: dict[str, Any] = {
            "format": format_selector,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 0,
            "merge_output_format": "mp4",
        }
        if target_video is not None:
            ydl_opts["outtmpl"] = str(target_video)
        if sort_rule:
            ydl_opts["format_sort"] = sort_rule
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=download)
        except download_error_type as exc:
            raise map_download_error(
                str(exc),
                project_id=project_id,
                job_id=job_id,
                retryable=True,
            ) from exc

        if download and target_video is not None and not target_video.exists():
            raise IngestError(
                code=INGEST_INVALID_SOURCE,
                message=f"download completed but target video missing: {target_video}",
                retryable=True,
                context={"stage": "ingest"},
            )
        return info if isinstance(info, dict) else {}
