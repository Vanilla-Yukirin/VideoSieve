"""WS gateway for job-scoped events and control commands."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
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

    def connect(
        self, *, job_id: str, socket: WebSocketLike, after_cursor: int | None = None
    ) -> None:
        """Attach a websocket, replay missed events, then send an authoritative snapshot."""

        if after_cursor is not None and after_cursor < 0:
            raise ValueError("after_cursor must be non-negative")
        self._connections[job_id].add(socket)
        self._control_plane.ensure_job_tracking(job_id)
        channel = f"jobs:{job_id}"
        barrier_cursor = self._event_bus.latest_cursor(channel)
        replay_cursor = after_cursor
        while replay_cursor is not None:
            events = self._event_bus.list_after(
                channel,
                after_cursor=replay_cursor,
                limit=1000,
            )
            if not events:
                break
            for event in events:
                if event.event_id is None or event.event_id > barrier_cursor:
                    break
                socket.send_json(self._event_payload(event))
                replay_cursor = int(event.event_id or replay_cursor)
            if replay_cursor >= barrier_cursor or len(events) < 1000:
                break
        snapshot = self._control_plane.get_job_snapshot(job_id)
        socket.send_json(
            {
                "event_type": "snapshot",
                "cursor": barrier_cursor,
                "state_version": snapshot.state_version,
                "request_id": None,
                "payload": snapshot.model_dump(mode="json"),
            }
        )
        self._ensure_ws_subscription(job_id, after_cursor=barrier_cursor)

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
        before = self._control_plane.get_job_snapshot(job_id)
        ack = self._control_plane.dispatch_control_command(
            job_id=job_id,
            command=command.command,
            request_id=command.request_id,
        )
        if command.request_id is not None:
            ack["request_id"] = command.request_id
        try:
            snapshot = self._control_plane.get_job_snapshot(job_id)
        except KeyError:
            snapshot = None
        if not bool(ack.get("accepted")):
            phase = "rejected"
        elif snapshot is None or snapshot.control_phase != "accepted":
            phase = "applied"
        else:
            phase = "accepted"
        event_payload: dict[str, object] = dict(ack)
        event_payload.update(
            {
                "phase": phase,
                "confirmed": phase == "applied",
                "execution_state": snapshot.status if snapshot is not None else "deleted",
                "requested_action": (
                    snapshot.requested_action if snapshot is not None else None
                ),
            }
        )
        self._event_bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="control_ack",
                project_id=snapshot.project_id if snapshot is not None else before.project_id,
                job_id=job_id,
                payload=event_payload,
                ts=datetime.now(UTC).isoformat(),
                state_version=(
                    snapshot.state_version if snapshot is not None else before.state_version + 1
                ),
                request_id=command.request_id,
            ),
        )
        return ack

    def _ensure_ws_subscription(self, job_id: str, *, after_cursor: int | None = None) -> None:
        if job_id in self._subscriptions:
            return

        def _handler(event: InfraEvent) -> None:
            self._fanout(event)

        self._subscriptions[job_id] = self._event_bus.subscribe(
            f"jobs:{job_id}",
            _handler,
            after_cursor=after_cursor,
        )

    def _fanout(self, event: InfraEvent) -> None:
        payload = self._event_payload(event)
        for socket in list(self._connections.get(event.job_id, ())):
            socket.send_json(payload)

    def _event_payload(self, event: InfraEvent) -> dict[str, Any]:
        return {
            "event_type": event.event_type,
            "project_id": event.project_id,
            "job_id": event.job_id,
            "payload": event.payload,
            "ts": event.ts,
            "cursor": int(event.event_id or 0),
            "state_version": int(event.state_version or 0),
            "request_id": event.request_id,
        }
