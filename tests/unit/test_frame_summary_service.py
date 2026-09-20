from __future__ import annotations

import json
from pathlib import Path

from frame_summary import FrameSummaryResult, FrameSummaryService
from infra import FileSystemWorkspaceStore
from keyframes import KeyframeBaselineService


class _StaticFrameSummaryProvider:
    @property
    def adapter_name(self) -> str:
        return "test_static"

    def summarize_frame(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> FrameSummaryResult:
        del image_path
        return FrameSummaryResult(
            frame_id=frame_id,
            lang=language_hint or "und",
            provider=self.adapter_name,
            description_text=f"summary for {frame_id}",
        )


def test_frame_summary_reads_keyframes_and_writes_jsonl(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    keyframes = KeyframeBaselineService(store)
    keyframes.run(
        "project-1", "job-1", duration_seconds=11.0, interval_seconds=5.0, reason="sample"
    )

    service = FrameSummaryService(store, _StaticFrameSummaryProvider())
    rows = service.run("project-1", "job-1", language_hint="zh")

    summary_file = store.frame_summary_file("project-1", "job-1")
    assert summary_file.exists()
    assert len(rows) == 3

    lines = [json.loads(line) for line in summary_file.read_text(encoding="utf-8").splitlines()]
    assert [line["frame_id"] for line in lines] == ["frame_000001", "frame_000002", "frame_000003"]

    for line in lines:
        assert set(line) == {
            "schema_version",
            "frame_id",
            "lang",
            "provider",
            "description_text",
        }
        assert line["schema_version"] == "1.1"
        assert line["lang"] == "zh"
        assert line["provider"] == "test_static"
        assert isinstance(line["description_text"], str)
        assert line["description_text"]


def test_frame_summary_handles_missing_keyframes_file(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = FrameSummaryService(store, _StaticFrameSummaryProvider())

    rows = service.run("project-2", "job-2")

    assert rows == []
    assert store.frame_summary_file("project-2", "job-2").exists()
    assert store.frame_summary_file("project-2", "job-2").read_text(encoding="utf-8") == ""
