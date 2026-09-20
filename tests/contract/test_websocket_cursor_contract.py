from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from apps.api.models import JobCreateRequest, ProjectCreateRequest
from apps.api.service import ApiControlPlane
from apps.api.ws_gateway import JobWebSocketGateway

from infra import FileSystemWorkspaceStore, InfraEvent, SQLiteEventBus, SQLiteJobRepository


class _Socket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_json(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)


def _runtime(
    db_path: Path,
    workspace_path: Path,
) -> tuple[ApiControlPlane, JobWebSocketGateway, SQLiteEventBus, SQLiteJobRepository]:
    repository = SQLiteJobRepository(db_path)
    repository.ensure_schema()
    event_bus = SQLiteEventBus(db_path, poll_interval_seconds=0.01)
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(workspace_path),
        event_bus=event_bus,
    )
    gateway = JobWebSocketGateway(control_plane=control_plane, event_bus=event_bus)
    return control_plane, gateway, event_bus, repository


def test_reconnect_replays_missed_events_then_sends_authoritative_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "contract-test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")
    db_path = tmp_path / "infra.db"
    workspace_path = tmp_path / "workspaces"

    control_plane, gateway, event_bus, repository = _runtime(db_path, workspace_path)
    project_id = control_plane.create_project(ProjectCreateRequest(title="cursor contract"))
    job_id = control_plane.create_job(JobCreateRequest(project_id=project_id))

    first_socket = _Socket()
    gateway.connect(job_id=job_id, socket=first_socket)
    first_snapshot = first_socket.messages[-1]
    assert first_snapshot["event_type"] == "snapshot"
    assert isinstance(first_snapshot["cursor"], int)
    assert first_snapshot["state_version"] == first_snapshot["payload"]["state_version"]
    assert first_snapshot["request_id"] is None
    last_seen = first_snapshot["cursor"]
    gateway.disconnect(job_id=job_id, socket=first_socket)
    event_bus.close()
    repository.close()

    producer_after_api_exit = SQLiteEventBus(db_path, poll_interval_seconds=0.01)
    producer_after_api_exit.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="progress",
            project_id=project_id,
            job_id=job_id,
            payload={"stage": "asr", "pct": 40},
        ),
    )
    producer_after_api_exit.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="log",
            project_id=project_id,
            job_id=job_id,
            payload={"level": "info", "message": "persisted while API was down"},
            request_id="request-written-while-api-down",
        ),
    )
    expected_latest_cursor = producer_after_api_exit.latest_cursor(f"jobs:{job_id}")
    producer_after_api_exit.close()

    _, restarted_gateway, restarted_bus, restarted_repository = _runtime(
        db_path,
        workspace_path,
    )
    reconnect_socket = _Socket()
    restarted_gateway.connect(
        job_id=job_id,
        socket=reconnect_socket,
        after_cursor=last_seen,
    )

    assert [message["event_type"] for message in reconnect_socket.messages] == [
        "progress",
        "log",
        "snapshot",
    ]
    cursors = [message["cursor"] for message in reconnect_socket.messages]
    assert cursors[:-1] == sorted(cursors[:-1])
    assert len(set(cursors[:-1])) == 2
    assert all(cursor > last_seen for cursor in cursors[:-1])
    assert cursors[-1] == expected_latest_cursor
    assert all(isinstance(message["state_version"], int) for message in reconnect_socket.messages)
    assert reconnect_socket.messages[1]["request_id"] == "request-written-while-api-down"
    assert reconnect_socket.messages[-1]["request_id"] is None
    assert reconnect_socket.messages[-1]["payload"]["job_id"] == job_id

    restarted_gateway.disconnect(job_id=job_id, socket=reconnect_socket)
    restarted_bus.close()
    restarted_repository.close()


def test_control_ack_round_trips_request_id_without_faking_execution_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "contract-test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")
    db_path = tmp_path / "infra.db"
    control_plane, gateway, event_bus, repository = _runtime(
        db_path,
        tmp_path / "workspaces",
    )
    project_id = control_plane.create_project(ProjectCreateRequest(title="control contract"))
    job_id = control_plane.create_job(JobCreateRequest(project_id=project_id))
    claimed = repository.claim_next_job("worker-1")
    assert claimed is not None
    channel = f"jobs:{job_id}"
    before_command_cursor = event_bus.latest_cursor(channel)

    ack = gateway.handle_command(
        job_id=job_id,
        payload={"command": "pause", "request_id": "web-command-1"},
    )

    assert ack["accepted"] is True
    assert ack["request_id"] == "web-command-1"
    requested = repository.get_job(job_id)
    assert requested is not None
    assert requested.status == "running"
    assert requested.control_command == "pause"
    assert requested.control_request_id == "web-command-1"
    assert requested.control_version > requested.control_ack_version

    reconnect_socket = _Socket()
    gateway.connect(
        job_id=job_id,
        socket=reconnect_socket,
        after_cursor=before_command_cursor,
    )
    assert [message["event_type"] for message in reconnect_socket.messages] == [
        "control_ack",
        "snapshot",
    ]
    ack_envelope = reconnect_socket.messages[0]
    assert ack_envelope["request_id"] == "web-command-1"
    assert ack_envelope["state_version"] == requested.state_version
    assert ack_envelope["cursor"] > before_command_cursor
    assert ack_envelope["payload"]["confirmed"] is False
    assert ack_envelope["payload"]["phase"] == "accepted"
    assert ack_envelope["payload"]["execution_state"] == "running"
    assert ack_envelope["payload"]["requested_action"] == "pause"
    assert reconnect_socket.messages[1]["state_version"] == requested.state_version

    gateway.disconnect(job_id=job_id, socket=reconnect_socket)
    event_bus.close()
    repository.close()


def test_cancel_without_worker_is_persisted_as_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "contract-test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")
    control_plane, gateway, event_bus, repository = _runtime(
        tmp_path / "infra.db",
        tmp_path / "workspaces",
    )
    project_id = control_plane.create_project(ProjectCreateRequest(title="cancel contract"))
    job_id = control_plane.create_job(JobCreateRequest(project_id=project_id))
    before_cursor = event_bus.latest_cursor(f"jobs:{job_id}")

    ack = gateway.handle_command(
        job_id=job_id,
        payload={"command": "cancel", "request_id": "cancel-queued-1"},
    )

    assert ack["accepted"] is True
    job = repository.get_job(job_id)
    assert job is not None
    assert job.status == "cancelled"
    assert job.control_ack_version == job.control_version
    events = event_bus.list_after(
        f"jobs:{job_id}",
        after_cursor=before_cursor,
    )
    assert len(events) == 1
    assert events[0].payload["phase"] == "applied"
    assert events[0].payload["confirmed"] is True
    assert events[0].payload["execution_state"] == "cancelled"
    assert events[0].payload["requested_action"] is None

    event_bus.close()
    repository.close()
