from __future__ import annotations

import json
from pathlib import Path

from workers.celery_app import WorkerRuntime

from contracts import JobStatus
from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository
from pipeline import PipelineOrchestrator
from pipeline.models import STAGE_SEQUENCE


def _make_runtime(
    tmp_path: Path, *, project_id: str = "p1", job_id: str = "j1"
) -> tuple[WorkerRuntime, SQLiteJobRepository, FileSystemWorkspaceStore]:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project(project_id, title="demo", status=JobStatus.QUEUED.value)
    repository.create_job(job_id, project_id, status=JobStatus.QUEUED.value, stage=None)
    runtime = WorkerRuntime(
        PipelineOrchestrator(
            repository=repository,
            workspace=workspace,
            event_bus=RedisEventBus(stub_mode=True),
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

    checkpoint_path = workspace.path("p1", "meta", "pipeline.checkpoint.json")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["completed_stages"] == [stage.value for stage in STAGE_SEQUENCE]
    assert checkpoint["reused_until_stage"] is None
    assert all(value == "succeeded" for value in checkpoint["stage_statuses"].values())

    assert workspace.path("p1", "asr", "transcript.jsonl").exists()
    assert workspace.path("p1", "fusion", "timeline.json").exists()
    assert workspace.path("p1", "outputs", "summary.json").exists()

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED.value
