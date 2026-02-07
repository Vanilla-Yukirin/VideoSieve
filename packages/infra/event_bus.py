"""Event bus abstractions and minimal Redis-compatible stub implementation."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable

from .interfaces import EventBus, EventHandler, EventSubscription
from .models import InfraEvent


class _InMemorySubscription(EventSubscription):
    def __init__(self, on_unsubscribe: Callable[[], None]) -> None:
        self._on_unsubscribe = on_unsubscribe
        self._active = True

    def unsubscribe(self) -> None:
        if not self._active:
            return
        self._active = False
        self._on_unsubscribe()


class RedisEventBus(EventBus):
    """Redis-oriented event bus abstraction.

    Stub mode is enabled by default and uses in-memory fanout so tests and
    local bootstrap work without a Redis runtime dependency.
    """

    def __init__(self, *, stub_mode: bool = True) -> None:
        self._stub_mode = stub_mode
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def publish(self, channel: str, event: InfraEvent) -> None:
        if not self._stub_mode:
            raise NotImplementedError("live Redis publish is not implemented yet")

        message = json.dumps(
            {
                "event_type": event.event_type,
                "project_id": event.project_id,
                "job_id": event.job_id,
                "payload": event.payload,
                "ts": event.ts,
            }
        )
        decoded = json.loads(message)
        dispatched = InfraEvent(
            event_type=decoded["event_type"],
            project_id=decoded["project_id"],
            job_id=decoded["job_id"],
            payload=decoded["payload"],
            ts=decoded["ts"],
        )

        for handler in list(self._handlers[channel]):
            handler(dispatched)

    def subscribe(self, channel: str, handler: EventHandler) -> EventSubscription:
        if not self._stub_mode:
            raise NotImplementedError("live Redis subscribe is not implemented yet")

        self._handlers[channel].append(handler)

        def _remove() -> None:
            handlers = self._handlers[channel]
            if handler in handlers:
                handlers.remove(handler)

        return _InMemorySubscription(on_unsubscribe=_remove)

    def close(self) -> None:
        self._handlers.clear()
