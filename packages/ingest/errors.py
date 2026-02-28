"""Domain errors and error-code mapping for ingest stage."""

from __future__ import annotations

from core import VideoSieveError

INGEST_SOURCE_NOT_FOUND = "INGEST_SOURCE_NOT_FOUND"
INGEST_INVALID_SOURCE = "INGEST_INVALID_SOURCE"
INGEST_DOWNLOAD_FAILED = "INGEST_DOWNLOAD_FAILED"
INGEST_AUTH_REQUIRED = "INGEST_AUTH_REQUIRED"
INGEST_DEPENDENCY_MISSING = "INGEST_DEPENDENCY_MISSING"
INGEST_CANCELLED = "INGEST_CANCELLED"

_CANCEL_MARKER = "__videosieve_cancel_requested__"


def cancel_marker() -> str:
    """Return stable marker used to surface ingest cancellation."""

    return _CANCEL_MARKER


class IngestError(VideoSieveError):
    """Base ingest domain error."""


def map_download_error(
    message: str,
    *,
    project_id: str,
    job_id: str,
    retryable: bool,
) -> IngestError:
    """Convert raw downloader errors to stable ingest error codes."""

    lowered = message.lower()
    context = {"project_id": project_id, "job_id": job_id, "stage": "ingest"}
    if _CANCEL_MARKER in lowered:
        return IngestError(
            code=INGEST_CANCELLED,
            message="ingest cancelled by control command",
            retryable=False,
            context=context,
        )
    if "sign in" in lowered or "login" in lowered or "cookie" in lowered:
        return IngestError(
            code=INGEST_AUTH_REQUIRED,
            message=message,
            hint=(
                "Provide valid bilibili cookies via cookie_id/cookie_secret_ref "
                "or cookie_file_path (migration fallback)."
            ),
            retryable=False,
            context=context,
        )
    if "403" in lowered or "forbidden" in lowered:
        return IngestError(
            code=INGEST_DOWNLOAD_FAILED,
            message=message,
            hint="Access forbidden. Check region lock and cookie authorization.",
            retryable=retryable,
            context=context,
        )
    return IngestError(
        code=INGEST_DOWNLOAD_FAILED,
        message=message,
        hint="Downloader failed. Retry or verify the source URL and network connectivity.",
        retryable=retryable,
        context=context,
    )
