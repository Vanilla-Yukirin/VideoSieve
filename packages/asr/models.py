"""Typed models for ASR requests, responses, and segments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRANSCRIPT_SCHEMA_VERSION = "1.1"


@dataclass(slots=True)
class ASRRequest:
    """Input payload for one ASR invocation."""

    audio_path: Path
    hotwords: tuple[str, ...] = ()
    language_hint: str | None = None


@dataclass(slots=True)
class ASRSegment:
    """One transcript segment aligned with the data contract."""

    segment_id: str
    start: float
    end: float
    text: str
    lang: str
    conf: float | None = None

    def to_contract_dict(self) -> dict[str, Any]:
        """Serialize into one canonical transcript JSONL record."""

        record: dict[str, Any] = {
            "schema_version": TRANSCRIPT_SCHEMA_VERSION,
            "segment_id": self.segment_id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "lang": self.lang,
        }
        if self.conf is not None:
            record["conf"] = self.conf
        return record


@dataclass(slots=True)
class ASRResult:
    """Provider output including segments and adapter metadata."""

    segments: list[ASRSegment]
    metadata: dict[str, Any] = field(default_factory=dict)
