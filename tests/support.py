"""Explicit test doubles shared by focused unit and contract tests."""

from __future__ import annotations

from asr import ASRProvider, ASRRequest, ASRResult, ASRSegment


class StubASRProvider(ASRProvider):
    """Deterministic ASR double that cannot be selected by production config."""

    def __init__(self, default_texts: tuple[str, ...] | None = None) -> None:
        self._default_texts = default_texts or (
            "This is a test ASR segment.",
            "This output exists only inside the test suite.",
        )

    @property
    def adapter_name(self) -> str:
        return "test_stub"

    def transcribe(self, request: ASRRequest) -> ASRResult:
        lang = request.language_hint or "und"
        hotwords = tuple(request.hotwords)
        segments: list[ASRSegment] = []
        cursor = 0.0
        for index, text in enumerate(self._default_texts, start=1):
            end = cursor + 5.0
            normalized = text
            if index == 1 and hotwords:
                normalized = f"{text} Hotwords: {', '.join(hotwords)}"
            segments.append(
                ASRSegment(
                    segment_id=f"seg_{index:05d}",
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
                "provider_kind": "test_double",
            },
        )
