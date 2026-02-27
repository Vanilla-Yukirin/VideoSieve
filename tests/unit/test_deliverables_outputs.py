from __future__ import annotations

import json
from pathlib import Path

import pytest

from deliverables import DeliverablesService
from infra import FileSystemWorkspaceStore


def test_deliverables_writes_expected_files_and_content(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)
    project_id = "project-deliverables-1"
    job_id = "job-1"

    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_payload = {
        "schema_version": "1.0",
        "project_id": project_id,
        "job_id": job_id,
        "chunks": [
            {
                "chunk_id": "ch_0001",
                "start": 0.0,
                "end": 5.0,
                "text": "first chunk",
                "transcript_refs": ["seg_0001"],
                "frame_refs": ["frame_000001"],
                "frame_summary_refs": ["frame_000001:summary"],
            }
        ],
    }
    timeline_path.write_text(
        json.dumps(timeline_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = service.run(project_id, job_id=job_id)

    clean_path = store.clean_transcript_file(project_id, job_id)
    notes_path = store.illustrated_notes_file(project_id, job_id)
    summary_path = store.summary_file(project_id, job_id)

    assert result.clean_transcript_path == str(clean_path)
    assert result.illustrated_notes_path == str(notes_path)
    assert result.summary_path == str(summary_path)

    assert clean_path.exists()
    assert notes_path.exists()
    assert summary_path.exists()

    assert "first chunk" in clean_path.read_text(encoding="utf-8")
    notes_text = notes_path.read_text(encoding="utf-8")
    assert "[[frame:slide_000001]]" in notes_text
    assert "first chunk" in notes_text

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert set(summary_payload.keys()) == {"schema_version", "title", "summary"}
    assert summary_payload["schema_version"] == "1.0"
    assert "first chunk" in summary_payload["summary"]


def test_deliverables_missing_or_empty_timeline_behavior(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)

    with pytest.raises(FileNotFoundError):
        service.run("project-deliverables-missing", job_id="job-missing")

    project_id = "project-deliverables-empty"
    job_id = "job-empty"
    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": job_id,
                "chunks": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service.run(project_id, job_id=job_id)
    assert "(empty)" in store.clean_transcript_file(project_id, job_id).read_text(encoding="utf-8")
    assert "(empty)" in store.illustrated_notes_file(project_id, job_id).read_text(encoding="utf-8")
