"""Ingest package for local import and URL download MVP."""

from .errors import (
    INGEST_AUTH_REQUIRED,
    INGEST_DEPENDENCY_MISSING,
    INGEST_DOWNLOAD_FAILED,
    INGEST_INVALID_SOURCE,
    INGEST_SOURCE_NOT_FOUND,
    IngestError,
)
from .models import IngestMeta, IngestRequest, IngestResult
from .service import run_ingest, run_local_ingest, run_url_ingest

__all__ = [
    "INGEST_AUTH_REQUIRED",
    "INGEST_DEPENDENCY_MISSING",
    "INGEST_DOWNLOAD_FAILED",
    "INGEST_INVALID_SOURCE",
    "INGEST_SOURCE_NOT_FOUND",
    "IngestError",
    "IngestMeta",
    "IngestRequest",
    "IngestResult",
    "run_ingest",
    "run_local_ingest",
    "run_url_ingest",
]
