from __future__ import annotations

import json
from pathlib import Path

import pytest

from infra import FileSystemWorkspaceStore
from keyframes import ALLOWED_KEYFRAME_REASONS, KeyframeBaselineService


def test_keyframes_baseline_writes_jsonl_with_canonical_fields(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeBaselineService(store)
    job_id = "job-1"

    records = service.run(
        "project-1", job_id, duration_seconds=12.0, interval_seconds=5.0, reason="sample"
    )

    keyframes_file = store.keyframes_file("project-1", job_id)
    assert keyframes_file.exists()
    assert len(records) == 3

    lines = [json.loads(line) for line in keyframes_file.read_text(encoding="utf-8").splitlines()]
    assert [line["ts"] for line in lines] == [0.0, 5.0, 10.0]

    for line in lines:
        assert line["schema_version"] == "1.0"
        assert line["reason"] in ALLOWED_KEYFRAME_REASONS
        assert set(line) == {"schema_version", "frame_id", "ts", "path", "hash", "score", "reason"}
        assert line["path"].startswith(
            str(tmp_path / "workspaces" / "project-1" / "jobs" / job_id / "frames" / "images")
        )


def test_keyframes_baseline_rejects_invalid_reason(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeBaselineService(store)

    with pytest.raises(ValueError):
        service.run("project-2", "job-2", duration_seconds=5.0, reason="invalid")
