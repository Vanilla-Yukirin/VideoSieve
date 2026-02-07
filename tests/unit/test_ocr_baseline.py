from __future__ import annotations

import json
from pathlib import Path

from infra import FileSystemWorkspaceStore
from keyframes import KeyframeBaselineService
from ocr import MockOCRProvider, OCRBaselineService


def test_ocr_baseline_reads_keyframes_and_writes_jsonl(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    keyframes = KeyframeBaselineService(store)
    keyframes.run("project-1", duration_seconds=11.0, interval_seconds=5.0, reason="sample")

    ocr_service = OCRBaselineService(store, MockOCRProvider())
    rows = ocr_service.run("project-1", language_hint="zh")

    ocr_file = store.ocr_file("project-1")
    assert ocr_file.exists()
    assert len(rows) == 3

    lines = [json.loads(line) for line in ocr_file.read_text(encoding="utf-8").splitlines()]
    assert [line["frame_id"] for line in lines] == ["frame_000001", "frame_000002", "frame_000003"]

    for line in lines:
        assert set(line) == {"schema_version", "frame_id", "lang", "conf", "blocks"}
        assert line["schema_version"] == "1.0"
        assert line["lang"] == "zh"
        assert isinstance(line["blocks"], list)
        assert line["blocks"]
        assert set(line["blocks"][0]) == {"text", "bbox", "conf"}


def test_ocr_baseline_handles_missing_keyframes_file(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = OCRBaselineService(store, MockOCRProvider())

    rows = service.run("project-2")

    assert rows == []
    assert store.ocr_file("project-2").exists()
    assert store.ocr_file("project-2").read_text(encoding="utf-8") == ""
