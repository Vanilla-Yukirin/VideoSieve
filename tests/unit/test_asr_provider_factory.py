from __future__ import annotations

import pytest

from asr import FunASRLocalProvider, create_asr_provider_from_env


def test_factory_defaults_to_real_funasr_instead_of_mock(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOSIEVE_ASR_PROVIDER", raising=False)

    provider = create_asr_provider_from_env()

    assert isinstance(provider, FunASRLocalProvider)
    assert provider.adapter_name == "funasr_local"


@pytest.mark.parametrize("provider_name", ["", "unknown", "baseline", "mock"])
def test_factory_rejects_non_production_provider(monkeypatch, provider_name: str) -> None:
    monkeypatch.setenv("VIDEOSIEVE_ASR_PROVIDER", provider_name)

    with pytest.raises(ValueError, match="VIDEOSIEVE_ASR_PROVIDER"):
        create_asr_provider_from_env()


def test_factory_selects_funasr_local(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOSIEVE_ASR_PROVIDER", "funasr_local")
    monkeypatch.setenv("VIDEOSIEVE_ASR_MODEL", "FunAudioLLM/Fun-ASR-Nano-2512")
    monkeypatch.setenv("VIDEOSIEVE_ASR_HUB", "ms")
    monkeypatch.setenv("VIDEOSIEVE_ASR_DEVICE", "cpu")

    provider = create_asr_provider_from_env()

    assert isinstance(provider, FunASRLocalProvider)
    assert provider.adapter_name == "funasr_local"
