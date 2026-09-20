from __future__ import annotations

import json
from pathlib import Path

import pytest

from asr import BaselineASRProvider
from contracts import JobStatus, StageName
from frame_summary import FrameSummaryResult
from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository
from pipeline import PipelineOrchestrator


class _StaticFrameSummaryProvider:
    DEFAULT_PROMPT_ZH = "test zh prompt"
    DEFAULT_PROMPT_EN = "test en prompt"

    def __init__(self, **_kwargs: object) -> None:
        pass

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
            provider="test_static",
            description_text=f"summary for {frame_id}",
        )


def test_rerun_from_stage_preserves_prior_stage_status_and_sets_reuse_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pipeline.orchestrator.QwenFrameSummaryProvider",
        _StaticFrameSummaryProvider,
    )
    monkeypatch.setattr("pipeline.orchestrator._is_cv2_available", lambda: False)
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project("p1", title="demo", status=JobStatus.QUEUED.value)
    repository.create_job("j1", "p1", status=JobStatus.QUEUED.value, stage=None)

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.ensure_job_layout("p1", "j1")
    workspace.config_snapshot_file("p1", "j1").write_text(
        json.dumps(
            {
                "frame_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "frame-model",
                    "concurrency": 1,
                    "rpm": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    orchestrator = PipelineOrchestrator(
        repository=repository,
        workspace=workspace,
        event_bus=RedisEventBus(stub_mode=True),
        asr_provider=BaselineASRProvider(),
    )

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    first = orchestrator.run_job(project_id="p1", job_id="j1", source_path=str(source))
    assert first.status == JobStatus.SUCCEEDED.value

    repository.update_project_status("p1", JobStatus.PAUSED.value)
    repository.update_job_status("j1", status=JobStatus.PAUSED.value, stage=StageName.ASR.value)
    rerun = orchestrator.run_job(
        project_id="p1",
        job_id="j1",
        source_path=str(source),
        rerun_from_stage=StageName.ASR,
    )

    assert rerun.status == JobStatus.SUCCEEDED.value
    assert rerun.reused_until_stage == StageName.HOTWORDS.value

    checkpoint_path = workspace.job_path("p1", "j1", "meta", "pipeline.checkpoint.json")
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["stage_statuses"][StageName.INGEST.value] == "succeeded"
    assert payload["stage_statuses"][StageName.HOTWORDS.value] == "succeeded"
    assert payload["stage_statuses"][StageName.INGEST.value] != "skipped"
    assert payload["stage_statuses"][StageName.HOTWORDS.value] != "skipped"
    assert payload["reused_until_stage"] == StageName.HOTWORDS.value
