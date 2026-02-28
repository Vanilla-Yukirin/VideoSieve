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


def test_publish_log_does_not_raise_when_worker_log_write_fails(tmp_path: Path) -> None:
    orchestrator, _, bus = _make_orchestrator(tmp_path)
    received: list[InfraEvent] = []
    bus.subscribe("jobs:j1", received.append)

    blocking_parent = tmp_path / "blocked"
    blocking_parent.write_text("not a directory", encoding="utf-8")
    orchestrator._workspace.worker_log_file = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: blocking_parent / "worker.log"
    )

    orchestrator._publish_log("p1", "j1", level="info", message="hello")

    assert len(received) == 2
    assert received[0].event_type == "log"
    assert received[0].payload["level"] == "warning"
    assert "日志写入失败" in str(received[0].payload["message"])
    assert received[1].event_type == "log"
    assert received[1].payload == {"level": "info", "message": "hello"}


def test_cancel_command_sets_cancel_requested_state(tmp_path: Path) -> None:
    orchestrator, repository, _ = _make_orchestrator(tmp_path)
    repository.update_project_status("p1", JobStatus.RUNNING.value)
    repository.update_job_status("j1", status=JobStatus.RUNNING.value, stage="ingest")

    ack = orchestrator.handle_control_command(
        project_id="p1",
        job_id="j1",
        command=ControlCommandType.CANCEL,
    )
    assert ack["command"] == "cancel"
    assert ack["accepted"] is True

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    run = orchestrator.run_job(project_id="p1", job_id="j1", source_path=str(source))
    assert run.status == JobStatus.CANCELLED.value

    job = repository.get_job("j1")
    assert job is not None
    assert job.status == JobStatus.CANCELLED.value
