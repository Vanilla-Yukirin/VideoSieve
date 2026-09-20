from __future__ import annotations

import pytest

from asr import (
    ASRProviderError,
    CapsWriterWebSocketProvider,
    create_asr_provider_from_config,
    create_asr_provider_from_env,
)


def test_factory_defaults_to_explicit_unconfigured_error(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOSIEVE_ASR_PROVIDER", raising=False)

    with pytest.raises(ASRProviderError) as exc_info:
        create_asr_provider_from_env()

    assert exc_info.value.code == "ASR_PROVIDER_UNCONFIGURED"


@pytest.mark.parametrize("provider_name", ["unknown", "baseline", "mock", "funasr_local"])
def test_factory_rejects_unsupported_provider(provider_name: str) -> None:
    with pytest.raises(ASRProviderError) as exc_info:
        create_asr_provider_from_config({"provider": provider_name})

    assert exc_info.value.code == "ASR_PROVIDER_UNSUPPORTED"


def test_factory_rejects_empty_config() -> None:
    with pytest.raises(ASRProviderError) as exc_info:
        create_asr_provider_from_config({})

    assert exc_info.value.code == "ASR_PROVIDER_UNCONFIGURED"


def test_factory_defaults_capswriter_to_upstream_websocket(monkeypatch) -> None:
    monkeypatch.delenv("CAPSWRITER_TOKEN", raising=False)

    provider = create_asr_provider_from_config(
        {"provider": "capswriter", "endpoint": "ws://localhost:6016"}
    )

    assert isinstance(provider, CapsWriterWebSocketProvider)


def test_factory_rejects_non_websocket_capswriter_transport() -> None:
    with pytest.raises(ASRProviderError) as exc_info:
        create_asr_provider_from_config(
            {
                "provider": "capswriter",
                "transport": "http",
                "endpoint": "http://localhost:6018",
            }
        )

    assert exc_info.value.code == "ASR_CONFIG_INVALID"
