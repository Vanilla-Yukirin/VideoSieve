from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from apps.api.models import JobCreateRequest, ProjectCreateRequest
from apps.api.service import ApiControlPlane
from apps.api.ws_gateway import JOB_WS_CHANNEL, JobWebSocketGateway

from contracts import JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, InMemoryEventBus, SQLiteJobRepository


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


class _FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_json(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)


class _PublishingSocket(_FakeSocket):
    def __init__(self, *, publish_during_replay: Callable[[], None]) -> None:
        super().__init__()
        self._publish_during_replay = publish_during_replay
        self._published = False

    def send_json(self, payload: dict[str, Any]) -> None:
        super().send_json(payload)
        if payload["event_type"] == "progress" and not self._published:
            self._published = True
            self._publish_during_replay()


class _FailingSocket:
    def send_json(self, _payload: dict[str, Any]) -> None:
        raise RuntimeError("socket write failed")


def _bootstrap(
    tmp_path: Path,
) -> tuple[ApiControlPlane, JobWebSocketGateway, str, str, InMemoryEventBus, SQLiteJobRepository]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = InMemoryEventBus()
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
    _, gateway, project_id, job_id, bus, repository = _bootstrap(tmp_path)
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
    control_events = [
        message for message in socket.messages if message["event_type"] == "control_ack"
    ]
    assert control_events[-1]["payload"]["phase"] == "applied"
    assert control_events[-1]["payload"]["confirmed"] is True
    job = repository.get_job(job_id)
    assert job is not None
    assert job.control_ack_version == job.control_version


def test_ws_buffers_live_events_until_replay_and_snapshot_finish(tmp_path: Path) -> None:
    _, gateway, project_id, job_id, bus, _ = _bootstrap(tmp_path)
    channel = f"jobs:{job_id}"
    bus.publish(
        channel,
        InfraEvent(
            event_type="progress",
            project_id=project_id,
            job_id=job_id,
            payload={"stage": "asr", "pct": 10.0},
        ),
    )
    first_socket = _FakeSocket()
    gateway.connect(job_id=job_id, socket=first_socket)

    def _publish_live() -> None:
        bus.publish(
            channel,
            InfraEvent(
                event_type="log",
                project_id=project_id,
                job_id=job_id,
                payload={"level": "info", "message": "published during replay"},
            ),
        )

    socket = _PublishingSocket(publish_during_replay=_publish_live)
    gateway.connect(job_id=job_id, socket=socket, after_cursor=0)

    assert [message["event_type"] for message in socket.messages] == [
        "progress",
        "snapshot",
        "log",
    ]
    snapshot_cursor = socket.messages[1]["cursor"]
    assert socket.messages[0]["cursor"] <= snapshot_cursor
    assert socket.messages[2]["cursor"] > snapshot_cursor
    assert first_socket.messages[-1]["event_type"] == "log"

    gateway.disconnect(job_id=job_id, socket=first_socket)
    gateway.disconnect(job_id=job_id, socket=socket)


def test_ws_connect_failure_releases_socket_and_subscriptions(tmp_path: Path) -> None:
    control_plane, gateway, _, job_id, bus, _ = _bootstrap(tmp_path)
    socket = _FailingSocket()

    with pytest.raises(RuntimeError, match="socket write failed"):
        gateway.connect(job_id=job_id, socket=socket)

    assert job_id not in gateway._connections
    assert job_id not in gateway._subscriptions
    assert job_id not in control_plane._subscriptions
    assert bus._handlers[f"jobs:{job_id}"] == []


def test_ws_missing_job_is_rejected_before_tracking_or_subscription(tmp_path: Path) -> None:
    control_plane, gateway, _, _, bus, _ = _bootstrap(tmp_path)
    socket = _FakeSocket()

    with pytest.raises(KeyError, match="job not found"):
        gateway.connect(job_id="j_missing", socket=socket)

    assert "j_missing" not in gateway._connections
    assert "j_missing" not in gateway._subscriptions
    assert "j_missing" not in control_plane._subscriptions
    assert bus._handlers["jobs:j_missing"] == []
