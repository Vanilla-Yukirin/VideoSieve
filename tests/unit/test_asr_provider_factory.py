from __future__ import annotations

from asr import BaselineASRProvider, FunASRLocalProvider, create_asr_provider_from_env


def test_factory_defaults_to_baseline(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOSIEVE_ASR_PROVIDER", raising=False)
    provider = create_asr_provider_from_env()
    assert isinstance(provider, BaselineASRProvider)


def test_factory_selects_funasr_local(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOSIEVE_ASR_PROVIDER", "funasr_local")
    monkeypatch.setenv("VIDEOSIEVE_ASR_MODEL", "FunAudioLLM/Fun-ASR-Nano-2512")
    monkeypatch.setenv("VIDEOSIEVE_ASR_HUB", "ms")
    monkeypatch.setenv("VIDEOSIEVE_ASR_DEVICE", "cpu")

    provider = create_asr_provider_from_env()

    assert isinstance(provider, FunASRLocalProvider)
    assert provider.adapter_name == "funasr_local"
