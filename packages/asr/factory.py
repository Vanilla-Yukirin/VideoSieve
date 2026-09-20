"""Factory helpers for selecting external ASR providers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .interfaces import ASRProvider, ASRProviderError


def create_asr_provider_from_config(config: Mapping[str, object]) -> ASRProvider:
    """Create an ASR adapter from a job snapshot without persisting credentials."""

    provider = str(config.get("provider") or "").strip().lower()
    if provider in {"", "unconfigured"}:
        raise ASRProviderError(
            "ASR_PROVIDER_UNCONFIGURED",
            "ASR provider is not configured; select an external provider in system settings",
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
