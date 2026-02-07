from __future__ import annotations

import json
from pathlib import Path

from contracts import JobStatus, StageName
from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository
from pipeline import PipelineOrchestrator


def test_rerun_from_stage_preserves_prior_stage_status_and_sets_reuse_metadata(
    tmp_path: Path,
) -> None:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project("p1", title="demo", status=JobStatus.QUEUED.value)
    repository.create_job("j1", "p1", status=JobStatus.QUEUED.value, stage=None)

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    orchestrator = PipelineOrchestrator(
        repository=repository,
        workspace=workspace,
        event_bus=RedisEventBus(stub_mode=True),
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

    checkpoint_path = workspace.path("p1", "meta", "pipeline.checkpoint.json")
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["stage_statuses"][StageName.INGEST.value] == "succeeded"
    assert payload["stage_statuses"][StageName.HOTWORDS.value] == "succeeded"
    assert payload["stage_statuses"][StageName.INGEST.value] != "skipped"
    assert payload["stage_statuses"][StageName.HOTWORDS.value] != "skipped"
    assert payload["reused_until_stage"] == StageName.HOTWORDS.value
