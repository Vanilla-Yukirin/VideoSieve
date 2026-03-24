from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from asr import ASRRequest
from asr.funasr_local import FunASRLocalProvider, _as_seconds


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
