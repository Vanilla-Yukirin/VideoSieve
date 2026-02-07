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

    timeline_path = store.path(project_id, "fusion", "timeline.json")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_payload = {
        "schema_version": "1.0",
        "project_id": project_id,
        "job_id": "job-1",
        "chunks": [
            {
                "chunk_id": "ch_0001",
                "start": 0.0,
                "end": 5.0,
                "text": "first chunk",
                "transcript_refs": ["seg_0001"],
                "frame_refs": ["frame_000001"],
                "ocr_refs": ["frame_000001:block_0001"],
            }
        ],
    }
    timeline_path.write_text(
        json.dumps(timeline_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = service.run(project_id, job_id="job-1")

    clean_path = store.path(project_id, "outputs", "clean_transcript.md")
    notes_path = store.path(project_id, "outputs", "illustrated_notes.md")
    summary_path = store.path(project_id, "outputs", "summary.json")

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
    timeline_path = store.path(project_id, "fusion", "timeline.json")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": "job-empty",
                "chunks": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service.run(project_id, job_id="job-empty")
    assert "(empty)" in store.path(project_id, "outputs", "clean_transcript.md").read_text(
        encoding="utf-8"
    )
    assert "(empty)" in store.path(project_id, "outputs", "illustrated_notes.md").read_text(
        encoding="utf-8"
    )
