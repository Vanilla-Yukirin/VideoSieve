from __future__ import annotations

from pathlib import Path

from contracts import ControlCommandType, JobStatus
from core import INVALID_STATE_TRANSITION
from infra import FileSystemWorkspaceStore, InfraEvent, RedisEventBus, SQLiteJobRepository
from pipeline import PipelineOrchestrator


def _make_orchestrator(
    tmp_path: Path,
) -> tuple[PipelineOrchestrator, SQLiteJobRepository, RedisEventBus]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project("p1", title="demo", status=JobStatus.QUEUED.value)
    repository.create_job("j1", "p1", status=JobStatus.QUEUED.value, stage=None)
    bus = RedisEventBus(stub_mode=True)
    orchestrator = PipelineOrchestrator(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    return orchestrator, repository, bus


def test_resume_queued_returns_invalid_transition_and_emits_control_ack(tmp_path: Path) -> None:
    orchestrator, _, bus = _make_orchestrator(tmp_path)
    received: list[InfraEvent] = []
    bus.subscribe("jobs:j1", received.append)

    payload = orchestrator.handle_control_command(
        project_id="p1",
        job_id="j1",
        command=ControlCommandType.RESUME,
    )

    assert payload == {
        "command": "resume",
        "accepted": False,
        "reason": "resume only valid while paused",
        "code": INVALID_STATE_TRANSITION,
    }
    assert received
    assert received[-1].event_type == "control_ack"
    assert received[-1].payload == payload


def test_pause_command_is_applied_at_next_safety_point(tmp_path: Path) -> None:
    orchestrator, repository, _ = _make_orchestrator(tmp_path)
    repository.update_project_status("p1", JobStatus.RUNNING.value)
    repository.update_job_status("j1", status=JobStatus.RUNNING.value, stage=None)

    ack = orchestrator.handle_control_command(
        project_id="p1",
        job_id="j1",
        command=ControlCommandType.PAUSE,
    )
    assert ack["command"] == "pause"
    assert ack["accepted"] is True
    assert "reason" not in ack
    assert "code" not in ack

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    run = orchestrator.run_job(project_id="p1", job_id="j1", source_path=str(source))
    assert run.status == JobStatus.PAUSED.value

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.PAUSED.value
