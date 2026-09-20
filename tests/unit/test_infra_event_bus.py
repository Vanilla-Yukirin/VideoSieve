from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from infra import InfraEvent, InMemoryEventBus, SQLiteEventBus, SQLiteJobRepository


def test_in_memory_event_bus_publish_subscribe() -> None:
    bus = InMemoryEventBus()
    received: list[InfraEvent] = []

    subscription = bus.subscribe("jobs", received.append)
    bus.publish(
        "jobs",
        InfraEvent(
            event_type="progress",
            project_id="p-1",
            job_id="j-1",
            payload={"stage": "asr", "pct": 15},
        ),
    )

    assert len(received) == 1
    assert received[0].event_type == "progress"
    assert received[0].payload["pct"] == 15

    subscription.unsubscribe()
    bus.publish(
        "jobs",
        InfraEvent(
            event_type="progress",
            project_id="p-1",
            job_id="j-1",
            payload={"stage": "asr", "pct": 30},
        ),
    )
    assert len(received) == 1

    bus.close()


def test_sqlite_subscription_continues_after_handler_failure(tmp_path: Path) -> None:
    bus = SQLiteEventBus(tmp_path / "infra.db", poll_interval_seconds=0.01)
    channel = "jobs:j-handler-retry"
    bus.publish(
        channel,
        InfraEvent(
            event_type="poison",
            project_id="p-1",
            job_id="j-handler-retry",
            payload={},
        ),
    )
    bus.publish(
        channel,
        InfraEvent(
            event_type="progress",
            project_id="p-1",
            job_id="j-handler-retry",
            payload={"pct": 50},
        ),
    )
    delivered = threading.Event()
    received: list[str] = []

    def _handler(event: InfraEvent) -> None:
        if event.event_type == "poison":
            raise RuntimeError("consumer rejected one event")
        received.append(event.event_type)
        delivered.set()

    subscription = bus.subscribe(channel, _handler, after_cursor=0)
    try:
        assert delivered.wait(2.0)
        assert received == ["progress"]
    finally:
        subscription.unsubscribe()
        bus.close()


def test_sqlite_subscription_retries_transient_database_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = SQLiteEventBus(tmp_path / "infra.db", poll_interval_seconds=0.01)
    channel = "jobs:j-db-retry"
    bus.publish(
        channel,
        InfraEvent(
            event_type="progress",
            project_id="p-1",
            job_id="j-db-retry",
            payload={"pct": 75},
        ),
    )
    original = SQLiteJobRepository.list_job_events
    failed_once = False

    def _flaky_list_job_events(
        repository: SQLiteJobRepository,
        requested_channel: str,
        *,
        after_event_id: int,
        limit: int = 1000,
    ) -> list[InfraEvent]:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise sqlite3.OperationalError("database is temporarily busy")
        return original(
            repository,
            requested_channel,
            after_event_id=after_event_id,
            limit=limit,
        )

    monkeypatch.setattr(SQLiteJobRepository, "list_job_events", _flaky_list_job_events)
    delivered = threading.Event()
    subscription = bus.subscribe(channel, lambda _event: delivered.set(), after_cursor=0)
    try:
        assert delivered.wait(2.0)
        assert failed_once is True
    finally:
        subscription.unsubscribe()
        bus.close()
