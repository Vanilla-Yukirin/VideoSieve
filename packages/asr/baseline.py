"""Baseline mock ASR provider for local testing and scaffolding."""

from __future__ import annotations

from .interfaces import ASRProvider
from .models import ASRRequest, ASRResult, ASRSegment


class BaselineASRProvider(ASRProvider):
    """Deterministic mock provider without external SDK dependencies."""

    def __init__(self, default_texts: tuple[str, ...] | None = None) -> None:
        self._default_texts = default_texts or (
            "This is a baseline ASR segment.",
            "Replace this provider with a real adapter later.",
        )

    @property
    def adapter_name(self) -> str:
        return "baseline_mock"

    def transcribe(self, request: ASRRequest) -> ASRResult:
        lang = request.language_hint or "und"
        hotwords = tuple(request.hotwords)

        segments: list[ASRSegment] = []
        cursor = 0.0
        for idx, text in enumerate(self._default_texts, start=1):
            end = cursor + 5.0
            normalized = text
            if idx == 1 and hotwords:
                normalized = f"{text} Hotwords: {', '.join(hotwords)}"
            segments.append(
                ASRSegment(
                    segment_id=f"seg_{idx:05d}",
                    start=cursor,
                    end=end,
                    text=normalized,
                    lang=lang,
                    conf=0.9,
                )
            )
            cursor = end

        return ASRResult(
            segments=segments,
            metadata={
                "adapter_name": self.adapter_name,
                "language_hint": request.language_hint,
                "hotwords": list(hotwords),
                "audio_path": str(request.audio_path),
                "provider_kind": "stub",
            },
        )
