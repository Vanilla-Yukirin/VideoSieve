"""VLM text-extraction provider protocol and result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OCRBlock:
    """One OCR text block with confidence and bbox."""

    text: str
    bbox: tuple[int, int, int, int]
    conf: float

    def to_json(self) -> dict[str, object]:
        return {
            "text": self.text,
            "bbox": list(self.bbox),
            "conf": self.conf,
        }


@dataclass(frozen=True)
class OCRFrameResult:
    """One OCR JSONL row for ``ocr/ocr.jsonl``."""

    frame_id: str
    lang: str
    conf: float
    blocks: tuple[OCRBlock, ...]
    summary_text: str
    provider: str

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "frame_id": self.frame_id,
            "lang": self.lang,
            "conf": self.conf,
            "provider": self.provider,
            "summary_text": self.summary_text,
            "blocks": [block.to_json() for block in self.blocks],
        }


class OCRProvider(Protocol):
    """Adapter interface for OCR providers."""

    def recognize(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> OCRFrameResult:
        """Return OCR result for one frame image."""
        ...
