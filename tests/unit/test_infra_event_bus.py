from __future__ import annotations

import pytest

from infra import InfraEvent, RedisEventBus


def test_redis_event_bus_stub_publish_subscribe() -> None:
    bus = RedisEventBus(stub_mode=True)
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


def test_redis_event_bus_non_stub_is_not_implemented() -> None:
    bus = RedisEventBus(stub_mode=False)

    with pytest.raises(NotImplementedError):
        bus.subscribe("jobs", lambda event: None)
