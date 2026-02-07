"""Data models for keyframe baseline output."""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "1.0"
ALLOWED_KEYFRAME_REASONS: frozenset[str] = frozenset({"stable", "scene", "cluster", "sample"})


@dataclass(frozen=True)
class KeyframeRecord:
    """One keyframe JSONL row for ``frames/keyframes.jsonl``."""

    frame_id: str
    ts: float
    path: str
    hash: str
    score: float
    reason: str

    def to_json(self) -> dict[str, object]:
        """Serialize this record to the canonical JSONL shape."""
        if self.reason not in ALLOWED_KEYFRAME_REASONS:
            raise ValueError(f"invalid keyframe reason: {self.reason}")
        return {
            "schema_version": SCHEMA_VERSION,
            "frame_id": self.frame_id,
            "ts": self.ts,
            "path": self.path,
            "hash": self.hash,
            "score": self.score,
            "reason": self.reason,
        }
