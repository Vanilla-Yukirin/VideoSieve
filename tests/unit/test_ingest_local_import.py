from __future__ import annotations

import json
from pathlib import Path

import pytest

from infra import FileSystemWorkspaceStore
from ingest import IngestRequest, run_local_ingest


def test_run_local_ingest_writes_source_and_meta(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    source_file = tmp_path / "input" / "demo.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"fake-video-bytes")

    request = IngestRequest(
        project_id="p_ingest_1",
        job_id="j_ingest_1",
        source_path=str(source_file),
        title="PyTorch Transformer",
        description="介绍 Transformer 与 Attention",
        tags=["PyTorch", "深度学习"],
        language_hint="zh",
    )

    result = run_local_ingest(workspace, request)

    target_video = workspace.source_video_file("p_ingest_1")
    target_meta = workspace.meta_file("p_ingest_1")

    assert target_video.exists()
    assert target_video.read_bytes() == b"fake-video-bytes"
    assert target_meta.exists()

    meta_payload = json.loads(target_meta.read_text(encoding="utf-8"))
    assert meta_payload["project_id"] == "p_ingest_1"
    assert meta_payload["job_id"] == "j_ingest_1"
    assert meta_payload["source_type"] == "local_file"
    assert meta_payload["source_ref"] == str(source_file.resolve())
    assert meta_payload["title"] == "PyTorch Transformer"

    assert result.project_id == "p_ingest_1"
    assert result.job_id == "j_ingest_1"
    assert result.source_video_path == str(target_video)
    assert result.meta_path == str(target_meta)


def test_run_local_ingest_uses_source_stem_when_title_is_missing(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    source_file = tmp_path / "input" / "lecture_01.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"small")

    request = IngestRequest(
        project_id="p_ingest_2",
        job_id="j_ingest_2",
        source_path=str(source_file),
    )

    result = run_local_ingest(workspace, request)

    assert result.meta.title == "lecture_01"


def test_run_local_ingest_rejects_missing_or_non_file_source(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")

    missing = IngestRequest(project_id="p", job_id="j", source_path=str(tmp_path / "missing.mp4"))
    with pytest.raises(FileNotFoundError):
        run_local_ingest(workspace, missing)

    folder = tmp_path / "folder_source"
    folder.mkdir(parents=True, exist_ok=True)
    not_file = IngestRequest(project_id="p", job_id="j", source_path=str(folder))
    with pytest.raises(ValueError):
        run_local_ingest(workspace, not_file)
