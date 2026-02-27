"""Frame summary provider protocol and result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FrameSummaryResult:
    """One JSONL row for ``frame_summary/frame_summary.jsonl``."""

    frame_id: str
    lang: str
    provider: str
    description_text: str

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "1.1",
            "frame_id": self.frame_id,
            "lang": self.lang,
            "provider": self.provider,
            "description_text": self.description_text,
        }


class FrameSummaryProvider(Protocol):
    """Adapter interface for frame summary providers."""

    def summarize_frame(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> FrameSummaryResult:
        """Return free-text frame summary for one image."""
        ...
