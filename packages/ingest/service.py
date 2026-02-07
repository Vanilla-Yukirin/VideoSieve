"""Local ingest service implementation."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from infra import WorkspaceStore

from .models import IngestMeta, IngestRequest, IngestResult


def _normalize_local_source(source_path: str) -> Path:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"local source file not found: {source}")
    if not source.is_file():
        raise ValueError(f"local source must be a file path: {source}")
    return source


def run_local_ingest(workspace: WorkspaceStore, request: IngestRequest) -> IngestResult:
    """Copy local media into workspace and emit `meta/meta.json`."""

    source = _normalize_local_source(request.source_path)

    workspace.ensure_project_layout(request.project_id)
    target_video = workspace.source_video_file(request.project_id)
    target_meta = workspace.meta_file(request.project_id)

    shutil.copy2(source, target_video)

    meta = IngestMeta(
        project_id=request.project_id,
        job_id=request.job_id,
        source_ref=str(source),
        title=request.title or source.stem,
        description=request.description,
        tags=request.tags,
        language_hint=request.language_hint,
        ingested_at=datetime.now(UTC),
    )
    target_meta.write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    return IngestResult(
        project_id=request.project_id,
        job_id=request.job_id,
        source_video_path=str(target_video),
        meta_path=str(target_meta),
        meta=meta,
    )
