from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from asr import ASRRequest
from asr.funasr_local import FunASRLocalProvider, _as_seconds, _segments_from_word_timestamps


def test_funasr_local_provider_maps_generate_result(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    class _FakeAutoModel:
        def __init__(self, **kwargs) -> None:
            observed["init"] = kwargs

        def generate(self, **kwargs):
            observed["generate"] = kwargs
            return [
                {
                    "text": "hello world",
                    "sentence_info": [
                        {"start": 0, "end": 1200, "text": "hello", "confidence": 0.9},
                        {"start": 1200, "end": 2400, "text": "world", "confidence": 0.8},
                    ],
                }
            ]

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=_FakeAutoModel))

    provider = FunASRLocalProvider(device="cpu", hub="ms")
    result = provider.transcribe(
        ASRRequest(
            audio_path=tmp_path / "media" / "audio.wav",
            hotwords=("VideoSieve",),
            language_hint="中文",
        )
    )

    assert observed["init"] is not None
    init_kwargs = observed["init"]
    assert isinstance(init_kwargs, dict)
    assert init_kwargs["model"] == "FunAudioLLM/Fun-ASR-Nano-2512"
    assert init_kwargs["hub"] == "ms"
    assert init_kwargs["device"] == "cpu"
    remote_code_path = str(init_kwargs["remote_code"]).replace("\\", "/")
    assert remote_code_path.endswith("packages/asr/vendor/fun_asr/model.py")

    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 1.2
    assert result.segments[0].text == "hello"
    assert result.segments[1].text == "world"
    assert result.metadata["provider_kind"] == "local"
    assert result.metadata["adapter_name"] == "funasr_local"


def test_funasr_local_provider_rejects_empty_payload(monkeypatch, tmp_path: Path) -> None:
    class _FakeAutoModel:
        def __init__(self, **kwargs) -> None:
            pass

        def generate(self, **kwargs):
            return []

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=_FakeAutoModel))

    provider = FunASRLocalProvider(device="cpu", hub="ms")
    with pytest.raises(RuntimeError, match="no transcript payload"):
        provider.transcribe(ASRRequest(audio_path=tmp_path / "media" / "audio.wav"))


def test_funasr_local_provider_restores_sys_path(monkeypatch, tmp_path: Path) -> None:
    class _FakeAutoModel:
        def __init__(self, **kwargs) -> None:
            pass

        def generate(self, **kwargs):
            return [{"text": "ok"}]

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=_FakeAutoModel))

    provider = FunASRLocalProvider(device="cpu", hub="ms")
    before = list(sys.path)
    provider.transcribe(ASRRequest(audio_path=tmp_path / "media" / "audio.wav"))
    after = list(sys.path)

    assert after == before


def test_as_seconds_supports_ms_int_and_s_float() -> None:
    assert _as_seconds(1500, default=0.0) == 1.5
    assert _as_seconds(1.5, default=0.0) == 1.5


def test_funasr_nano_word_timestamps_multi_sentence(monkeypatch, tmp_path: Path) -> None:
    """Fun-ASR-Nano returns 'timestamps' (word-level, seconds); verify sentence splitting."""

    class _FakeAutoModel:
        def __init__(self, **kwargs) -> None:
            pass

        def generate(self, **kwargs):
            return [
                {
                    "text": "你好世界。再见朋友。",
                    "timestamps": [
                        {"token": "你", "start_time": 0.0, "end_time": 0.2},
                        {"token": "好", "start_time": 0.2, "end_time": 0.4},
                        {"token": "世", "start_time": 0.4, "end_time": 0.6},
                        {"token": "界", "start_time": 0.6, "end_time": 0.8},
                        {"token": "。", "start_time": 0.8, "end_time": 0.9},
                        {"token": "再", "start_time": 1.0, "end_time": 1.2},
                        {"token": "见", "start_time": 1.2, "end_time": 1.4},
                        {"token": "朋", "start_time": 1.4, "end_time": 1.6},
                        {"token": "友", "start_time": 1.6, "end_time": 1.8},
                        {"token": "。", "start_time": 1.8, "end_time": 1.9},
                    ],
                }
            ]

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=_FakeAutoModel))

    provider = FunASRLocalProvider(device="cpu", hub="ms")
    result = provider.transcribe(ASRRequest(audio_path=tmp_path / "media" / "audio.wav"))

    assert len(result.segments) == 2
    assert result.segments[0].text == "你好世界。"
    assert result.segments[0].start >= 0.0
    assert result.segments[0].end > result.segments[0].start
    assert result.segments[1].text == "再见朋友。"
    assert result.segments[1].start >= result.segments[0].start


def test_funasr_nano_word_timestamps_single_sentence(monkeypatch, tmp_path: Path) -> None:
    """Single sentence with word timestamps produces one segment with real start/end."""

    class _FakeAutoModel:
        def __init__(self, **kwargs) -> None:
            pass

        def generate(self, **kwargs):
            return [
                {
                    "text": "hello world",
                    "timestamps": [
                        {"token": "hello", "start_time": 1.5, "end_time": 2.0},
                        {"token": "world", "start_time": 2.0, "end_time": 2.8},
                    ],
                }
            ]

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=_FakeAutoModel))

    provider = FunASRLocalProvider(device="cpu", hub="ms")
    result = provider.transcribe(ASRRequest(audio_path=tmp_path / "media" / "audio.wav"))

    assert len(result.segments) == 1
    assert result.segments[0].start == 1.5
    assert result.segments[0].end == 2.8
    assert result.segments[0].text == "hello world"


def test_segments_from_word_timestamps_empty_tokens() -> None:
    """Empty token list falls back to text-length duration estimate."""
    segs = _segments_from_word_timestamps("some text", [], language="und")
    assert len(segs) == 1
    assert segs[0].end >= 0.1
