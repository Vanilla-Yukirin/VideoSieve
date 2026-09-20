"""Persistent SQLite and process-local event bus implementations."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from .interfaces import EventBus, EventHandler, EventSubscription
from .models import InfraEvent
from .sqlite_repository import SQLiteJobRepository

logger = logging.getLogger(__name__)


class _InMemorySubscription(EventSubscription):
    def __init__(self, on_unsubscribe: Callable[[], None]) -> None:
        self._on_unsubscribe = on_unsubscribe
        self._active = True

    def unsubscribe(self) -> None:
        if not self._active:
            return
        self._active = False
        self._on_unsubscribe()


class InMemoryEventBus(EventBus):
    """Process-local event stream for focused tests and explicit embedding."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._events: dict[str, list[InfraEvent]] = defaultdict(list)
        self._next_event_id = 1

    def publish(self, channel: str, event: InfraEvent) -> None:
        message = json.dumps(
            {
                "event_type": event.event_type,
                "project_id": event.project_id,
                "job_id": event.job_id,
                "payload": event.payload,
                "ts": event.ts,
                "state_version": event.state_version,
                "request_id": event.request_id,
            }
        )
        decoded = json.loads(message)
        dispatched = InfraEvent(
            event_type=decoded["event_type"],
            project_id=decoded["project_id"],
            job_id=decoded["job_id"],
            payload=decoded["payload"],
            ts=decoded["ts"],
            event_id=self._next_event_id,
            state_version=decoded["state_version"],
            request_id=decoded["request_id"],
        )
        self._next_event_id += 1
        self._events[channel].append(dispatched)

        for handler in list(self._handlers[channel]):
            handler(dispatched)

    def subscribe(
        self,
        channel: str,
        handler: EventHandler,
        *,
        after_cursor: int | None = None,
    ) -> EventSubscription:
        self._handlers[channel].append(handler)

        def _remove() -> None:
            handlers = self._handlers[channel]
            if handler in handlers:
                handlers.remove(handler)

        return _InMemorySubscription(on_unsubscribe=_remove)

    def list_after(self, channel: str, *, after_cursor: int, limit: int = 1000) -> list[InfraEvent]:
        return [
            event
            for event in self._events[channel]
            if event.event_id is not None and event.event_id > after_cursor
        ][:limit]

    def latest_cursor(self, channel: str) -> int:
        events = self._events[channel]
        if not events:
            return 0
        return int(events[-1].event_id or 0)

    def close(self) -> None:
        self._handlers.clear()
        self._events.clear()


class _SQLiteSubscription(EventSubscription):
    def __init__(
        self,
        *,
        db_path: Path,
        channel: str,
        handler: EventHandler,
        after_cursor: int,
        poll_interval_seconds: float,
        on_unsubscribe: Callable[[_SQLiteSubscription], None],
    ) -> None:
        self._db_path = db_path
        self._channel = channel
        self._handler = handler
        self._cursor = after_cursor
        self._poll_interval_seconds = poll_interval_seconds
        self._on_unsubscribe = on_unsubscribe
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"sqlite-event-subscription-{channel}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def unsubscribe(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, self._poll_interval_seconds * 4))
        self._on_unsubscribe(self)

    def _run(self) -> None:
        repository: SQLiteJobRepository | None = None
        try:
            while not self._stop.wait(self._poll_interval_seconds):
                try:
                    if repository is None:
                        repository = SQLiteJobRepository(self._db_path)
                    events = repository.list_job_events(
                        self._channel,
                        after_event_id=self._cursor,
                        limit=1000,
                    )
                except sqlite3.Error:
                    logger.warning(
                        "transient SQLite event subscription error; polling will retry",
                        exc_info=True,
                        extra={"channel": self._channel, "after_cursor": self._cursor},
                    )
                    if repository is not None:
                        repository.close()
                        repository = None
                    continue
                except Exception:
                    logger.exception(
                        "SQLite event subscription stopped after an unexpected read error",
                        extra={"channel": self._channel, "after_cursor": self._cursor},
                    )
                    return

                for event in events:
                    if self._stop.is_set():
                        return
                    event_cursor = int(event.event_id or self._cursor)
                    try:
                        self._handler(event)
                    except Exception:
                        # One broken consumer must not silently kill the polling
                        # thread or block all later events behind a poison event.
                        logger.exception(
                            "SQLite event subscription handler failed; event skipped",
                            extra={
                                "channel": self._channel,
                                "event_id": event.event_id,
                            },
                        )
                    finally:
                        self._cursor = event_cursor
        finally:
            if repository is not None:
                repository.close()


class SQLiteEventBus(EventBus):
    """SQLite-backed cross-process event stream with cursor replay."""

    def __init__(self, db_path: str | Path, *, poll_interval_seconds: float = 0.1) -> None:
        self._db_path = Path(db_path)
        self._poll_interval_seconds = max(0.01, poll_interval_seconds)
        self._subscriptions: set[_SQLiteSubscription] = set()
        self._lock = threading.Lock()
        repository = SQLiteJobRepository(self._db_path)
        try:
            repository.ensure_schema()
        finally:
            repository.close()

    def publish(self, channel: str, event: InfraEvent) -> None:
        repository = SQLiteJobRepository(self._db_path)
        try:
            event.event_id = repository.append_job_event(channel, event)
        finally:
            repository.close()

    def subscribe(
        self,
        channel: str,
        handler: EventHandler,
        *,
        after_cursor: int | None = None,
    ) -> EventSubscription:
        subscription = _SQLiteSubscription(
            db_path=self._db_path,
            channel=channel,
            handler=handler,
            after_cursor=(
                self.latest_cursor(channel) if after_cursor is None else max(0, after_cursor)
            ),
            poll_interval_seconds=self._poll_interval_seconds,
            on_unsubscribe=self._remove_subscription,
        )
        with self._lock:
            self._subscriptions.add(subscription)
        try:
            subscription.start()
        except Exception:
            self._remove_subscription(subscription)
            raise
        return subscription

    def list_after(self, channel: str, *, after_cursor: int, limit: int = 1000) -> list[InfraEvent]:
        repository = SQLiteJobRepository(self._db_path)
        try:
            return repository.list_job_events(
                channel,
                after_event_id=after_cursor,
                limit=limit,
            )
        finally:
            repository.close()

    def latest_cursor(self, channel: str) -> int:
        repository = SQLiteJobRepository(self._db_path)
        try:
            return repository.latest_job_event_id(channel)
        finally:
            repository.close()

    def close(self) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            subscription.unsubscribe()

    def _remove_subscription(self, subscription: _SQLiteSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)
