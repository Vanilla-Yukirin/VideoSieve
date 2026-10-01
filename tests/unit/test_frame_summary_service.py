from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from frame_summary import FrameSummaryResult, FrameSummaryService
from frame_summary import service as frame_service
from infra import FileSystemWorkspaceStore
from keyframes import KeyframeBaselineService
from model_api import client as model_client


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


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _single_frame(store: FileSystemWorkspaceStore) -> None:
    frames = KeyframeBaselineService(store).run("project", "job", duration_seconds=1.0)
    Path(frames[0].path).write_bytes(b"synthetic-image")


@pytest.mark.parametrize("rpm", [0, 1])
def test_frame_retry_obeys_same_rpm_gate_and_excludes_wait_from_timing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rpm: int
) -> None:
    clock = _Clock()
    monkeypatch.setattr(model_client, "time", clock)
    monkeypatch.setattr(frame_service, "time", clock)
    sent_at: list[float] = []

    def send(*args: Any) -> tuple[dict[str, Any], None]:
        sent_at.append(clock.now)
        clock.sleep(0.25)
        return {
            "choices": [
                {
                    "finish_reason": "length" if len(sent_at) == 1 else "stop",
                    "message": {"content": "partial" if len(sent_at) == 1 else "complete"},
                }
            ],
        }, None

    monkeypatch.setattr(model_client, "_send_request", send)
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _single_frame(store)
    provider = frame_service.QwenFrameSummaryProvider(
        api_key="synthetic-key",
        endpoint="https://example.test/v1",
        model="test-model",
        allow_env_fallback=False,
        model_options={"max_retries": 1},
    )
    result = FrameSummaryService(store, provider).run("project", "job", concurrency=1, rpm=rpm)
    assert sent_at[0] == 1000.0  # Initial request consumes exactly one slot.
    assert len(sent_at) == 2
    if rpm:
        assert sent_at[1] - sent_at[0] >= 60.0
    else:
        assert sent_at[1] - sent_at[0] < 2.0
    assert result[0].description_text == "complete"
    assert [attempt.elapsed_ms for attempt in result[0].model_calls] == [250, 250]
    assert store.frame_summary_file("project", "job").exists()


def test_frame_retry_rate_wait_remains_cooperatively_cancellable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(model_client, "time", clock)
    monkeypatch.setattr(frame_service, "time", clock)
    sent = 0

    def send(*args: Any) -> tuple[dict[str, Any], None]:
        nonlocal sent
        sent += 1
        return {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}, None

    def check() -> None:
        if clock.now >= 1002.0:
            raise RuntimeError("cancel requested")

    monkeypatch.setattr(model_client, "_send_request", send)
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _single_frame(store)
    provider = frame_service.QwenFrameSummaryProvider(
        api_key="synthetic-key",
        endpoint="https://example.test/v1",
        model="test-model",
        allow_env_fallback=False,
        model_options={"max_retries": 1},
        check_control=check,
    )
    with pytest.raises(RuntimeError, match="cancel requested"):
        FrameSummaryService(store, provider).run("project", "job", concurrency=1, rpm=1)
    assert sent == 1
    assert clock.now < 1002.2  # Does not block through the rest of the 60s window.
    assert not store.frame_summary_file("project", "job").exists()
