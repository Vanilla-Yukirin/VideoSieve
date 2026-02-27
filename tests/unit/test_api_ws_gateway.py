from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from apps.api.models import JobCreateRequest, ProjectCreateRequest
from apps.api.service import ApiControlPlane
from apps.api.ws_gateway import JOB_WS_CHANNEL, JobWebSocketGateway

from contracts import JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, RedisEventBus, SQLiteJobRepository


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


class _FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_json(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)


def _bootstrap(
    tmp_path: Path,
) -> tuple[ApiControlPlane, JobWebSocketGateway, str, str, RedisEventBus, SQLiteJobRepository]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = RedisEventBus(stub_mode=True)
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    project_id = control_plane.create_project(ProjectCreateRequest(title="demo"))
    job_id = control_plane.create_job(JobCreateRequest(project_id=project_id))
    gateway = JobWebSocketGateway(control_plane=control_plane, event_bus=bus)
    return control_plane, gateway, project_id, job_id, bus, repository


def test_ws_primary_channel_reconnect_uses_snapshot_source_of_truth(tmp_path: Path) -> None:
    _, gateway, project_id, job_id, bus, repository = _bootstrap(tmp_path)

    socket = _FakeSocket()
    gateway.connect(job_id=job_id, socket=socket)

    assert JOB_WS_CHANNEL == "/ws/jobs/{job_id}"
    assert socket.messages[0]["event_type"] == "snapshot"
    assert socket.messages[0]["payload"]["job_id"] == job_id

    gateway.disconnect(job_id=job_id, socket=socket)

    repository.update_project_status(project_id, JobStatus.RUNNING.value)
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")

    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="progress",
            project_id=project_id,
            job_id=job_id,
            payload={"stage": "asr", "pct": 61.0},
        ),
    )

    reconnect_socket = _FakeSocket()
    gateway.connect(job_id=job_id, socket=reconnect_socket)
    reconnect_snapshot = reconnect_socket.messages[0]

    assert reconnect_snapshot["event_type"] == "snapshot"
    assert reconnect_snapshot["payload"]["status"] == JobStatus.RUNNING.value
    assert reconnect_snapshot["payload"]["current_stage"] == "asr"


def test_ws_forwards_events_and_handles_job_control_command(tmp_path: Path) -> None:
    _, gateway, project_id, job_id, bus, _ = _bootstrap(tmp_path)
    socket = _FakeSocket()
    gateway.connect(job_id=job_id, socket=socket)

    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="log",
            project_id=project_id,
            job_id=job_id,
            payload={"level": "info", "message": "hello"},
        ),
    )

    ack = gateway.handle_command(job_id=job_id, payload={"command": "cancel"})

    assert any(message["event_type"] == "log" for message in socket.messages)
    assert ack["command"] == "cancel"
    assert ack["accepted"] is True
