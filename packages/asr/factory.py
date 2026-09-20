"""Factory helpers for selecting external ASR providers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .capswriter import CapsWriterWebSocketProvider
from .interfaces import ASRProvider, ASRProviderError


def _config_str(config: Mapping[str, object], key: str, default: str = "") -> str:
    value = config.get(key)
    return str(value).strip() if value is not None else default


def _config_positive_int(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key)
    if isinstance(value, bool):
        return default
    try:
        return max(1, int(str(value))) if value is not None else default
    except ValueError:
        return default


def _config_nonnegative_float(config: Mapping[str, object], key: str, default: float) -> float:
    value = config.get(key)
    if isinstance(value, bool):
        return default
    try:
        return max(0.0, float(str(value))) if value is not None else default
    except ValueError:
        return default


def create_asr_provider_from_config(config: Mapping[str, object]) -> ASRProvider:
    """Create an ASR adapter from a job snapshot without persisting credentials."""

    provider = str(config.get("provider") or "").strip().lower()
    if provider in {"", "unconfigured"}:
        raise ASRProviderError(
            "ASR_PROVIDER_UNCONFIGURED",
            "ASR provider is not configured; select an external provider in system settings",
        )
    if provider == "capswriter":
        endpoint = _config_str(config, "endpoint")
        if not endpoint:
            raise ASRProviderError(
                "ASR_CONFIG_INVALID",
                "CapsWriter endpoint is required",
                hint="Set the CapsWriter endpoint in system settings.",
            )
        token_env = _config_str(config, "token_env", "CAPSWRITER_TOKEN")
        token = os.getenv(token_env, "").strip() or None
        language = _config_str(config, "language", "auto") or "auto"
        context = _config_str(config, "context")
        timeout_seconds = _config_positive_int(config, "timeout_seconds", 900)
        transport = _config_str(config, "transport", "websocket").lower()
        if transport != "websocket":
            raise ASRProviderError(
                "ASR_CONFIG_INVALID",
                f"unsupported CapsWriter transport: {transport}",
                hint="CapsWriter uses its official WebSocket protocol.",
            )
        return CapsWriterWebSocketProvider(
            endpoint=endpoint,
            token=token,
            language=language,
            context=context,
            timeout_seconds=timeout_seconds,
            ffmpeg_executable=_config_str(config, "ffmpeg_executable", "ffmpeg"),
            segment_seconds=max(
                1.0,
                _config_nonnegative_float(config, "segment_seconds", 60.0),
            ),
            overlap_seconds=_config_nonnegative_float(config, "overlap_seconds", 4.0),
        )
    raise ASRProviderError(
        "ASR_PROVIDER_UNSUPPORTED",
        f"unsupported ASR provider: {provider}",
    )


def create_asr_provider_from_env() -> ASRProvider:
    """Compatibility entry point for deployments that still select via env."""

    return create_asr_provider_from_config(
        {"provider": os.getenv("VIDEOSIEVE_ASR_PROVIDER", "unconfigured")}
    )
