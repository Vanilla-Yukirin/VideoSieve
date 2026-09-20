"""WS gateway for job-scoped events and control commands."""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
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


@dataclass(slots=True)
class _PendingConnection:
    """Buffer live events until replay and the authoritative snapshot finish."""

    socket: WebSocketLike
    cursor: int = 0
    ready: bool = False
    buffered_events: list[InfraEvent] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class JobWebSocketGateway:
    """Fanout gateway with snapshot-first reconnect semantics."""

    def __init__(self, *, control_plane: ApiControlPlane, event_bus: EventBus) -> None:
        self._control_plane = control_plane
        self._event_bus = event_bus
        self._connections: dict[str, set[WebSocketLike]] = defaultdict(set)
        self._subscriptions: dict[str, dict[WebSocketLike, EventSubscription]] = defaultdict(dict)

    def connect(
        self, *, job_id: str, socket: WebSocketLike, after_cursor: int | None = None
    ) -> None:
        """Attach a websocket, replay missed events, then send an authoritative snapshot."""

        if after_cursor is not None and after_cursor < 0:
            raise ValueError("after_cursor must be non-negative")
        if self._control_plane.get_job(job_id) is None:
            raise KeyError(f"job not found: {job_id}")
        if socket in self._connections.get(job_id, ()):
            raise ValueError("socket is already connected")

        channel = f"jobs:{job_id}"
        barrier_cursor = self._event_bus.latest_cursor(channel)
        if after_cursor is not None and after_cursor > barrier_cursor:
            raise ValueError("after_cursor is ahead of the persistent event stream")

        pending = _PendingConnection(socket=socket, cursor=barrier_cursor)

        def _handler(event: InfraEvent) -> None:
            self._deliver_live_event(pending, event)

        subscription: EventSubscription | None = None
        tracking_started = False
        try:
            # Subscribe at the first barrier before replay. Events published during
            # setup are buffered for this socket and cannot overtake its snapshot.
            subscription = self._event_bus.subscribe(
                channel,
                _handler,
                after_cursor=barrier_cursor,
            )
            catchup_cursor = self._event_bus.latest_cursor(channel)
            replay_cursor = barrier_cursor if after_cursor is None else after_cursor
            self._send_replay(
                channel=channel,
                socket=socket,
                after_cursor=replay_cursor,
                barrier_cursor=catchup_cursor,
            )

            tracking_started = True
            snapshot = self._control_plane.get_job_snapshot(job_id)
            socket.send_json(
                {
                    "event_type": "snapshot",
                    "cursor": catchup_cursor,
                    "state_version": snapshot.state_version,
                    "request_id": None,
                    "payload": snapshot.model_dump(mode="json"),
                }
            )
            self._activate_connection(pending, cursor=catchup_cursor)
            self._connections[job_id].add(socket)
            self._subscriptions[job_id][socket] = subscription
        except Exception:
            if subscription is not None:
                subscription.unsubscribe()
            sockets = self._connections.get(job_id)
            if sockets is not None:
                sockets.discard(socket)
                if not sockets:
                    self._connections.pop(job_id, None)
            subscriptions = self._subscriptions.get(job_id)
            if subscriptions is not None:
                subscriptions.pop(socket, None)
                if not subscriptions:
                    self._subscriptions.pop(job_id, None)
            if tracking_started and not self._connections.get(job_id):
                self._control_plane.release_job_tracking(job_id)
            raise

    def disconnect(self, *, job_id: str, socket: WebSocketLike) -> None:
        """Detach one websocket and clean idle subscriptions."""

        subscriptions = self._subscriptions.get(job_id)
        subscription = subscriptions.pop(socket, None) if subscriptions is not None else None
        if subscription is not None:
            subscription.unsubscribe()
        if subscriptions is not None and not subscriptions:
            self._subscriptions.pop(job_id, None)

        sockets = self._connections.get(job_id)
        if sockets is None:
            return
        sockets.discard(socket)
        if sockets:
            return

        self._connections.pop(job_id, None)
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
                "requested_action": (snapshot.requested_action if snapshot is not None else None),
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

    def _send_replay(
        self,
        *,
        channel: str,
        socket: WebSocketLike,
        after_cursor: int,
        barrier_cursor: int,
    ) -> None:
        cursor = after_cursor
        while cursor < barrier_cursor:
            events = self._event_bus.list_after(channel, after_cursor=cursor, limit=1000)
            if not events:
                return
            previous_cursor = cursor
            for event in events:
                event_cursor = int(event.event_id or 0)
                if event_cursor <= cursor:
                    continue
                if event_cursor > barrier_cursor:
                    return
                socket.send_json(self._event_payload(event))
                cursor = event_cursor
            if cursor == previous_cursor or len(events) < 1000:
                return

    def _deliver_live_event(self, pending: _PendingConnection, event: InfraEvent) -> None:
        event_cursor = int(event.event_id or 0)
        if event_cursor <= 0:
            return
        with pending.lock:
            if event_cursor <= pending.cursor:
                return
            if not pending.ready:
                pending.buffered_events.append(event)
                return
            pending.socket.send_json(self._event_payload(event))
            pending.cursor = event_cursor

    def _activate_connection(self, pending: _PendingConnection, *, cursor: int) -> None:
        with pending.lock:
            pending.cursor = max(pending.cursor, cursor)
            for event in sorted(
                pending.buffered_events,
                key=lambda item: int(item.event_id or 0),
            ):
                event_cursor = int(event.event_id or 0)
                if event_cursor <= pending.cursor:
                    continue
                pending.socket.send_json(self._event_payload(event))
                pending.cursor = event_cursor
            pending.buffered_events.clear()
            pending.ready = True

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
