from __future__ import annotations

from pathlib import Path

from apps.api.rest import (
    REST_ROUTES,
    control_job,
    create_job,
    create_project,
    get_job_snapshot,
    list_job_artifacts,
)
from apps.api.service import ApiControlPlane

from contracts import JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, RedisEventBus, SQLiteJobRepository


def _make_control_plane(
    tmp_path: Path,
) -> tuple[ApiControlPlane, SQLiteJobRepository, RedisEventBus]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = RedisEventBus(stub_mode=True)
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    return control_plane, repository, bus


def test_rest_project_job_snapshot_and_artifact_list(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    repository.update_project_status(project_id, JobStatus.RUNNING.value)
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.path(project_id, "outputs", "clean_transcript.md").write_text("ok", encoding="utf-8")

    # Prime one snapshot so the control plane starts event tracking for this job.
    get_job_snapshot(control_plane, job_id)

    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="log",
            project_id=project_id,
            job_id=job_id,
            payload={"level": "info", "message": "started"},
        ),
    )
    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="progress",
            project_id=project_id,
            job_id=job_id,
            payload={"stage": "asr", "pct": 27.5},
        ),
    )

    snapshot = get_job_snapshot(control_plane, job_id)
    artifacts = list_job_artifacts(control_plane, job_id)

    assert "GET /jobs/{job_id}/snapshot" in REST_ROUTES
    assert snapshot["status"] == JobStatus.RUNNING.value
    assert snapshot["current_stage"] == "asr"
    assert snapshot["progress"] == 27.5
    assert snapshot["latest_logs"] == ["[info] started"]
    assert any(item["path"] == "outputs/clean_transcript.md" for item in artifacts)


def test_rest_control_commands_are_job_scoped(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    for command in ("pause", "resume", "cancel", "delete"):
        ack = control_job(control_plane, job_id=job_id, command=command)
        assert ack["command"] == command
        assert "accepted" in ack

    job = repository.get_job(job_id)
    assert job is not None
    assert job.status in {
        JobStatus.QUEUED.value,
        JobStatus.PAUSED.value,
        JobStatus.RUNNING.value,
        JobStatus.CANCELLED.value,
    }
