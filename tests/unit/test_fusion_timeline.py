from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion import FusionService
from infra import FileSystemWorkspaceStore


def test_fusion_writes_timeline_with_required_chunk_fields(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = FusionService(store)
    project_id = "project-fusion-1"
    job_id = "job-1"

    transcript_path = store.transcript_file(project_id, job_id)
    keyframes_path = store.keyframes_file(project_id, job_id)
    frame_summary_path = store.frame_summary_file(project_id, job_id)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    keyframes_path.parent.mkdir(parents=True, exist_ok=True)
    frame_summary_path.parent.mkdir(parents=True, exist_ok=True)

    transcript_rows = [
        {
            "schema_version": "1.0",
            "segment_id": "seg_0001",
            "start": 0.0,
            "end": 4.0,
            "text": "intro",
            "lang": "en",
            "conf": 0.9,
        },
        {
            "schema_version": "1.0",
            "segment_id": "seg_0002",
            "start": 4.0,
            "end": 10.0,
            "text": "chapter one",
            "lang": "en",
            "conf": 0.9,
        },
    ]
    transcript_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in transcript_rows) + "\n",
        encoding="utf-8",
    )

    keyframes_rows = [
        {
            "schema_version": "1.0",
            "frame_id": "frame_000001",
            "ts": 1.0,
            "path": str(store.job_path(project_id, job_id, "frames", "images", "slide_000001.jpg")),
            "hash": "abc",
            "score": 1.0,
            "reason": "sample",
        },
        {
            "schema_version": "1.0",
            "frame_id": "frame_000002",
            "ts": 7.0,
            "path": str(store.job_path(project_id, job_id, "frames", "images", "slide_000002.jpg")),
            "hash": "def",
            "score": 1.0,
            "reason": "sample",
        },
    ]
    keyframes_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in keyframes_rows) + "\n",
        encoding="utf-8",
    )

    frame_summary_rows = [
        {
            "schema_version": "1.1",
            "frame_id": "frame_000001",
            "lang": "en",
            "provider": "qwen_frame_summary",
            "description_text": "Frame one summary",
        },
        {
            "schema_version": "1.1",
            "frame_id": "frame_000002",
            "lang": "en",
            "provider": "qwen_frame_summary",
            "description_text": "Frame two summary",
        },
    ]
    frame_summary_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in frame_summary_rows) + "\n",
        encoding="utf-8",
    )

    result = service.run(project_id, job_id=job_id)

    timeline_file = store.timeline_file(project_id, job_id)
    assert timeline_file.exists()
    assert result.timeline_path == str(timeline_file)

    payload = json.loads(timeline_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["project_id"] == project_id
    assert payload["job_id"] == job_id
    assert payload["chunks"]

    required_fields = {
        "chunk_id",
        "start",
        "end",
        "text",
        "transcript_refs",
        "frame_refs",
        "frame_summary_refs",
    }
    for chunk in payload["chunks"]:
        assert required_fields.issubset(set(chunk.keys()))


def test_fusion_missing_or_sparse_inputs_have_predictable_behavior(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = FusionService(store)

    with pytest.raises(FileNotFoundError):
        service.run("project-fusion-missing", job_id="job-missing")

    project_id = "project-fusion-sparse"
    job_id = "job-sparse"
    transcript_path = store.transcript_file(project_id, job_id)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "segment_id": "seg_0001",
                "start": 0.0,
                "end": 3.0,
                "text": "only transcript",
                "lang": "en",
                "conf": 0.9,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = service.run(project_id, job_id=job_id)
    payload = json.loads(Path(result.timeline_path).read_text(encoding="utf-8"))

    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["frame_refs"] == []
    assert payload["chunks"][0]["frame_summary_refs"] == []
