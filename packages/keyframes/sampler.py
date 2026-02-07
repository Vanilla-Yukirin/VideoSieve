"""Sampling helpers for baseline keyframe extraction."""

from __future__ import annotations


def stable_sampling_timestamps(
    duration_seconds: float,
    *,
    interval_seconds: float = 5.0,
) -> list[float]:
    """Return uniformly sampled timestamps within ``[0, duration)``."""
    if duration_seconds <= 0:
        return []
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    timestamps: list[float] = []
    cursor = 0.0
    while cursor < duration_seconds:
        timestamps.append(round(cursor, 3))
        cursor += interval_seconds
    return timestamps
