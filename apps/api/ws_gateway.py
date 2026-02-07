"""WS gateway for job-scoped events and control commands."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol

from infra import EventBus, EventSubscription, InfraEvent

from .models import WsControlCommand
from .service import ApiControlPlane

JOB_WS_CHANNEL = "/ws/jobs/{job_id}"


class WebSocketLike(Protocol):
    """Minimal websocket-like contract used by tests/runtime adapters."""

    def send_json(self, payload: dict[str, Any]) -> None:
        """Send one JSON event payload to client."""


class JobWebSocketGateway:
    """Fanout gateway with snapshot-first reconnect semantics."""

    def __init__(self, *, control_plane: ApiControlPlane, event_bus: EventBus) -> None:
        self._control_plane = control_plane
        self._event_bus = event_bus
        self._connections: dict[str, set[WebSocketLike]] = defaultdict(set)
        self._subscriptions: dict[str, EventSubscription] = {}

    def connect(self, *, job_id: str, socket: WebSocketLike) -> None:
        """Attach one websocket and push snapshot immediately."""

        self._connections[job_id].add(socket)
        self._control_plane.ensure_job_tracking(job_id)
        snapshot = self._control_plane.get_job_snapshot(job_id)
        socket.send_json({"event_type": "snapshot", "payload": snapshot.model_dump(mode="json")})
        self._ensure_ws_subscription(job_id)

    def disconnect(self, *, job_id: str, socket: WebSocketLike) -> None:
        """Detach one websocket and clean idle subscriptions."""

        sockets = self._connections.get(job_id)
        if sockets is None:
            return
        sockets.discard(socket)
        if sockets:
            return

        self._connections.pop(job_id, None)
        subscription = self._subscriptions.pop(job_id, None)
        if subscription is not None:
            subscription.unsubscribe()
        self._control_plane.release_job_tracking(job_id)

    def handle_command(self, *, job_id: str, payload: dict[str, Any]) -> dict[str, str | bool]:
        """Handle one WS client command on primary job channel."""

        command = WsControlCommand.model_validate(payload)
        return self._control_plane.dispatch_control_command(job_id=job_id, command=command.command)

    def _ensure_ws_subscription(self, job_id: str) -> None:
        if job_id in self._subscriptions:
            return

        def _handler(event: InfraEvent) -> None:
            self._fanout(event)

        self._subscriptions[job_id] = self._event_bus.subscribe(f"jobs:{job_id}", _handler)

    def _fanout(self, event: InfraEvent) -> None:
        payload = {
            "event_type": event.event_type,
            "project_id": event.project_id,
            "job_id": event.job_id,
            "payload": event.payload,
            "ts": event.ts,
        }
        for socket in list(self._connections.get(event.job_id, ())):
            socket.send_json(payload)
