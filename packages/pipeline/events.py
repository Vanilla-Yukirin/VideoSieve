"""Pipeline event publishing helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from infra import EventBus, InfraEvent


def publish_event(
    event_bus: EventBus,
    *,
    project_id: str,
    job_id: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    """Publish one job-scoped event envelope."""

    event_bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type=event_type,
            project_id=project_id,
            job_id=job_id,
            payload=payload,
            ts=datetime.now(UTC).isoformat(),
        ),
    )
