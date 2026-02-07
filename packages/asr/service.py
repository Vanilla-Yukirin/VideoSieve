"""ASR service helpers for provider invocation and transcript output."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .interfaces import ASRProvider
from .models import ASRRequest, ASRResult, ASRSegment


def serialize_transcript_lines(segments: Iterable[ASRSegment]) -> list[str]:
    """Serialize canonical transcript segment records to JSONL lines."""

    lines: list[str] = []
    for segment in segments:
        lines.append(json.dumps(segment.to_contract_dict(), ensure_ascii=False))
    return lines


def write_transcript_jsonl(
    provider: ASRProvider,
    *,
    audio_path: Path,
    output_path: Path,
    hotwords: tuple[str, ...] = (),
    language_hint: str | None = None,
) -> ASRResult:
    """Run one provider transcription and write `asr/transcript.jsonl`."""

    request = ASRRequest(
        audio_path=audio_path,
        hotwords=hotwords,
        language_hint=language_hint,
    )
    result = provider.transcribe(request)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = serialize_transcript_lines(result.segments)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
