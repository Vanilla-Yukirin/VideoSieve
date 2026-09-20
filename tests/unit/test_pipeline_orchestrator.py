from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.support import StubASRProvider
from workers.runtime import WorkerRuntime

from contracts import JobStatus
from frame_summary import FrameSummaryResult
from infra import FileSystemWorkspaceStore, InMemoryEventBus, SQLiteJobRepository
from ingest import INGEST_CANCELLED, IngestError
from keyframes import KeyframeStageError
from overall_summary import OverallSummaryProviderError, OverallSummaryResult
from pipeline import PipelineOrchestrator
from pipeline.models import STAGE_SEQUENCE


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


class _StaticOverallSummaryProvider:
    def __init__(self, *, model: str, **_kwargs: object) -> None:
        self.provider_name = "test_summary"
        self.model_name = model

    def summarize(
        self,
        source_text: str,
        *,
        language_hint: str | None,
        partial: bool,
    ) -> OverallSummaryResult:
        del language_hint, partial
        if self.model_name == "fail-model":
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_PROVIDER_UNAVAILABLE",
                "summary backend unavailable",
                retryable=True,
            )
        assert "test ASR segment" in source_text
        return OverallSummaryResult(
            text="real model-shaped test summary",
            provider=self.provider_name,
            model=self.model_name,
        )


@pytest.fixture(autouse=True)
def _real_providers_are_replaced_only_in_this_unit_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _write_test_keyframes(
        _video_path: Path,
        *,
        timestamps_to_paths: list[tuple[float, Path]],
    ) -> None:
        for _timestamp, output_path in timestamps_to_paths:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"test-keyframe")

    monkeypatch.setattr(
        "pipeline.orchestrator.QwenFrameSummaryProvider",
        _StaticFrameSummaryProvider,
    )
    monkeypatch.setattr(
        "pipeline.orchestrator.OpenAICompatibleSummaryProvider",
        _StaticOverallSummaryProvider,
    )
    monkeypatch.setattr("pipeline.orchestrator._is_cv2_available", lambda: True)
    monkeypatch.setattr(
        "pipeline.orchestrator.write_images_for_records",
        _write_test_keyframes,
    )


def _make_runtime(
    tmp_path: Path,
    *,
    project_id: str = "p1",
    job_id: str = "j1",
    worker_id: str | None = "test-worker",
) -> tuple[WorkerRuntime, SQLiteJobRepository, FileSystemWorkspaceStore]:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.ensure_job_layout(project_id, job_id)
    workspace.config_snapshot_file(project_id, job_id).write_text(
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
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project(project_id, title="demo", status=JobStatus.QUEUED.value)
    repository.create_job(job_id, project_id, status=JobStatus.QUEUED.value, stage=None)
    if worker_id is not None:
        claimed = repository.claim_next_job(worker_id)
        assert claimed is not None
    runtime = WorkerRuntime(
        PipelineOrchestrator(
            repository=repository,
            workspace=workspace,
            event_bus=InMemoryEventBus(),
            asr_provider=StubASRProvider(),
            worker_id=worker_id,
        )
    )
    return runtime, repository, workspace


def test_pipeline_orchestrates_all_stages_and_writes_checkpoint(tmp_path: Path) -> None:
    runtime, repository, workspace = _make_runtime(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    result = runtime.run_job(project_id="p1", job_id="j1", source_path=str(source), title="demo")

    assert result.status == JobStatus.SUCCEEDED.value
    assert result.completed_stages == [stage.value for stage in STAGE_SEQUENCE]

    checkpoint_path = workspace.job_path("p1", "j1", "meta", "pipeline.checkpoint.json")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["completed_stages"] == [stage.value for stage in STAGE_SEQUENCE]
    assert checkpoint["reused_until_stage"] is None
    assert all(value == "succeeded" for value in checkpoint["stage_statuses"].values())

    assert workspace.transcript_file("p1", "j1").exists()
    assert workspace.timeline_file("p1", "j1").exists()
    assert not workspace.summary_file("p1", "j1").exists()

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED.value


def test_pipeline_exits_early_when_job_already_cancelled(tmp_path: Path) -> None:
    runtime, repository, workspace = _make_runtime(tmp_path, worker_id=None)
    repository.update_job_status("j1", status=JobStatus.CANCELLED.value, stage=None)

    result = runtime.run_job(project_id="p1", job_id="j1")

    assert result.status == JobStatus.CANCELLED.value
    assert result.completed_stages == []
    checkpoint_path = workspace.job_path("p1", "j1", "meta", "pipeline.checkpoint.json")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["completed_stages"] == []

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.CANCELLED.value


def test_pipeline_reaches_model_backed_overall_summary_when_enabled(tmp_path: Path) -> None:
    runtime, repository, workspace = _make_runtime(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    workspace.ensure_job_layout("p1", "j1")
    workspace.config_snapshot_file("p1", "j1").write_text(
        json.dumps(
            {
                "summary_enabled": True,
                "frame_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "frame-model",
                    "concurrency": 1,
                    "rpm": 0,
                },
                "overall_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "summary-model",
                    "max_input_chars": 24000,
                },
            }
        ),
        encoding="utf-8",
    )

    result = runtime.run_job(project_id="p1", job_id="j1", source_path=str(source))

    assert result.status == JobStatus.SUCCEEDED.value
    payload = json.loads(workspace.summary_file("p1", "j1").read_text(encoding="utf-8"))
    assert payload["summary"] == "real model-shaped test summary"
    assert payload["provider"] == "test_summary"
    assert payload["model"] == "summary-model"
    assert repository.get_job("j1").status == JobStatus.SUCCEEDED.value  # type: ignore[union-attr]


def test_pipeline_preserves_overall_summary_provider_error_code(tmp_path: Path) -> None:
    runtime, repository, workspace = _make_runtime(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    workspace.ensure_job_layout("p1", "j1")
    workspace.config_snapshot_file("p1", "j1").write_text(
        json.dumps(
            {
                "summary_enabled": True,
                "frame_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "frame-model",
                    "concurrency": 1,
                    "rpm": 0,
                },
                "overall_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "fail-model",
                    "max_input_chars": 24000,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OverallSummaryProviderError):
        runtime.run_job(project_id="p1", job_id="j1", source_path=str(source))

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "OVERALL_SUMMARY_PROVIDER_UNAVAILABLE"
    assert not workspace.summary_file("p1", "j1").exists()


def test_pipeline_fails_when_selected_keyframe_images_are_not_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, repository, workspace = _make_runtime(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    def _drop_all_keyframes(
        _video_path: Path,
        *,
        timestamps_to_paths: list[tuple[float, Path]],
    ) -> None:
        del timestamps_to_paths

    monkeypatch.setattr(
        "pipeline.orchestrator.write_images_for_records",
        _drop_all_keyframes,
    )

    with pytest.raises(KeyframeStageError) as captured:
        runtime.run_job(project_id="p1", job_id="j1", source_path=str(source))

    assert captured.value.code == "KEYFRAME_IMAGES_INCOMPLETE"
    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "KEYFRAME_IMAGES_INCOMPLETE"
    assert not workspace.job_path("p1", "j1", "frames", "images.zip").exists()


def test_pipeline_cancel_during_ingest_does_not_flip_failed_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, repository, _ = _make_runtime(tmp_path)

    import pipeline.orchestrator as orchestrator_module

    def _cancelled_ingest(*_args: object, **_kwargs: object) -> object:
        repository.request_job_control("j1", "cancel")
        raise IngestError(
            code=INGEST_CANCELLED,
            message="ingest cancelled by control command",
            retryable=False,
        )

    monkeypatch.setattr(orchestrator_module, "run_ingest", _cancelled_ingest)

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    result = runtime.run_job(project_id="p1", job_id="j1", source_path=str(source))

    assert result.status == JobStatus.CANCELLED.value
    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.CANCELLED.value
