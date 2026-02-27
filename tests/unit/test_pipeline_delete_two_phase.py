from __future__ import annotations

from pathlib import Path

from contracts import ControlCommandType, JobStatus
from core import DELETE_PENDING_CLEANUP
from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository
from pipeline import PipelineOrchestrator


def test_delete_is_two_phase_and_returns_pending_cleanup_when_not_terminal(tmp_path: Path) -> None:
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

    ack = orchestrator.handle_control_command(
        project_id="p1",
        job_id="j1",
        command=ControlCommandType.DELETE,
    )
    assert ack == {
        "command": "delete",
        "accepted": True,
        "reason": "delete accepted, waiting for terminal state before cleanup",
        "code": DELETE_PENDING_CLEANUP,
    }

    workspace.ensure_job_layout("p1", "j1")
    assert workspace.job_root("p1", "j1").exists()

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    result = orchestrator.run_job(project_id="p1", job_id="j1", source_path=str(source))

    assert result.status == JobStatus.CANCELLED.value
    assert not workspace.job_root("p1", "j1").exists()
    assert workspace.project_root("p1").exists()
