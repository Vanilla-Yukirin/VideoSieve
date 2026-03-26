"""Local FunASR provider using official remote_code flow."""

from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .interfaces import ASRProvider
from .models import ASRRequest, ASRResult, ASRSegment


def _default_device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda:0"

    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"

    return "cpu"


def _vendor_remote_code_path() -> Path:
    return Path(__file__).resolve().parent / "vendor" / "fun_asr" / "model.py"


@contextmanager
def _temporary_sys_path(path: Path):
    path_str = str(path)
    original = list(sys.path)
    try:
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        yield
    finally:
        sys.path[:] = original


class FunASRLocalProvider(ASRProvider):
    """ASR provider backed by local FunASR inference.

    Note: VAD (Voice Activity Detection) is currently disabled due to a bug in funasr 1.3.1
    where inference_with_vad fails with KeyError when handling dict-format timestamps.

    For long videos (>10min), consider implementing external audio chunking before transcription.
    Current configuration works well for short-to-medium length videos.

    TODO: Add configurable chunking strategy for long-form content (split by duration or
    use external VAD like silero-vad, then transcribe chunks independently).
    """

    def __init__(
        self,
        *,
        model: str = "FunAudioLLM/Fun-ASR-Nano-2512",
        hub: str = "ms",
        device: str = "auto",
        language: str | None = None,
        itn: bool = True,
    ) -> None:
        self._model_id = model
        self._hub = hub
        self._device = _default_device() if device == "auto" else device
        self._language = language
        self._itn = itn
        self._model: Any | None = None

    @property
    def adapter_name(self) -> str:
        return "funasr_local"

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        vendor_root = _vendor_remote_code_path().parent
        with _temporary_sys_path(vendor_root):
            try:
                from funasr import AutoModel
            except Exception as exc:  # pragma: no cover - dependency/runtime path
                raise RuntimeError(
                    "funasr is not installed. Run `uv sync --extra asr_local --extra dev`."
                ) from exc

            self._model = AutoModel(
                model=self._model_id,
                trust_remote_code=True,
                remote_code=str(_vendor_remote_code_path()),
                device=self._device,
                hub=self._hub,
            )
        return self._model

    def transcribe(self, request: ASRRequest) -> ASRResult:
        model = self._ensure_model()

        language = request.language_hint or self._language
        kwargs: dict[str, Any] = {
            "input": [str(request.audio_path)],
            "cache": {},
            "batch_size": 1,
            "itn": self._itn,
        }
        if request.hotwords:
            kwargs["hotwords"] = list(request.hotwords)
        if language:
            kwargs["language"] = language

        raw = model.generate(**kwargs)
        segments = _parse_segments(raw, language=language or "und")

        metadata = {
            "adapter_name": self.adapter_name,
            "provider_kind": "local",
            "model": self._model_id,
            "hub": self._hub,
            "device": self._device,
            "language_hint": request.language_hint,
            "hotwords": list(request.hotwords),
            "audio_path": str(request.audio_path),
            "asr_cache_dir": os.getenv("MODELSCOPE_CACHE") or os.getenv("HF_HOME") or "default",
            "timestamp_source": "sentence_info_or_fallback",
        }
        return ASRResult(segments=segments, metadata=metadata)


def _parse_segments(payload: Any, *, language: str) -> list[ASRSegment]:
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("funasr returned no transcript payload")

    row = payload[0]
    if not isinstance(row, dict):
        text = str(row)
        if not text.strip():
            raise RuntimeError("funasr returned empty transcript row")
        return [
            ASRSegment(
                segment_id="seg_00001",
                start=0.0,
                end=max(0.1, len(text) * 0.08),
                text=text,
                lang=language,
                conf=1.0,
            )
        ]

    sentence_infos = row.get("sentence_info")
    if isinstance(sentence_infos, list) and sentence_infos:
        parsed: list[ASRSegment] = []
        for idx, item in enumerate(sentence_infos, start=1):
            if not isinstance(item, dict):
                continue
            start = _as_seconds(item.get("start"), default=0.0)
            end = _as_seconds(item.get("end"), default=start)
            text = str(item.get("text") or "")
            conf = _as_float(item.get("confidence"), default=1.0)
            parsed.append(
                ASRSegment(
                    segment_id=f"seg_{idx:05d}",
                    start=start,
                    end=end if end >= start else start,
                    text=text,
                    lang=language,
                    conf=conf,
                )
            )
        if parsed:
            return parsed

    text = str(row.get("text") or "")
    if not text.strip():
        raise RuntimeError("funasr returned empty transcript text")

    # Fun-ASR-Nano outputs word-level timestamps as {"token", "start_time", "end_time"} (seconds).
    word_timestamps = row.get("timestamps")
    if isinstance(word_timestamps, list) and word_timestamps:
        return _segments_from_word_timestamps(text, word_timestamps, language)

    duration = _estimate_duration_from_timestamp(row.get("timestamp"), text)
    return [
        ASRSegment(
            segment_id="seg_00001",
            start=0.0,
            end=duration,
            text=text,
            lang=language,
            conf=1.0,
        )
    ]


def _as_seconds(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        if value < 0:
            return default
        return float(value) / 1000.0
    if isinstance(value, float):
        if value < 0:
            return default
        return value
    return default


def _as_float(value: Any, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _estimate_duration_from_timestamp(timestamp: Any, text: str) -> float:
    if isinstance(timestamp, list) and timestamp:
        last = timestamp[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            end = _as_seconds(last[1], default=0.0)
            if end > 0:
                return end
    return max(0.1, len(text) * 0.08)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?\n])")


def _segments_from_word_timestamps(text: str, tokens: list[Any], language: str) -> list[ASRSegment]:
    """Build segments from Fun-ASR-Nano word-level timestamps.

    Each token dict has ``start_time`` and ``end_time`` in seconds.
    Sentences are split by punctuation; tokens are assigned proportionally.
    """
    valid = [t for t in tokens if isinstance(t, dict)]
    total_start = float(valid[0].get("start_time", 0.0)) if valid else 0.0
    total_end = float(valid[-1].get("end_time", 0.0)) if valid else max(0.1, len(text) * 0.08)
    total_end = max(total_end, total_start + 0.1)

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [
            ASRSegment(
                segment_id="seg_00001",
                start=total_start,
                end=total_end,
                text=text.strip(),
                lang=language,
                conf=1.0,
            )
        ]

    n_tokens = len(valid)
    total_chars = sum(len(s) for s in sentences)
    segments: list[ASRSegment] = []
    char_pos = 0
    for idx, sentence in enumerate(sentences, start=1):
        char_start = char_pos
        char_pos += len(sentence)
        # Proportional token slice for this sentence.
        t0 = round(char_start / total_chars * n_tokens)
        t1 = max(t0 + 1, round(char_pos / total_chars * n_tokens))
        t1 = min(t1, n_tokens)
        slice_ = valid[t0:t1]
        seg_start = float(slice_[0].get("start_time", total_start)) if slice_ else total_start
        seg_end = float(slice_[-1].get("end_time", seg_start)) if slice_ else seg_start
        seg_end = max(seg_end, seg_start + 0.1)
        segments.append(
            ASRSegment(
                segment_id=f"seg_{idx:05d}",
                start=seg_start,
                end=seg_end,
                text=sentence.strip(),
                lang=language,
                conf=1.0,
            )
        )
    return segments
