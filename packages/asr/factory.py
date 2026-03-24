"""Factory helpers for selecting ASR provider from environment."""

from __future__ import annotations

import os

from .baseline import BaselineASRProvider
from .funasr_local import FunASRLocalProvider
from .interfaces import ASRProvider


def create_asr_provider_from_env() -> ASRProvider:
    provider = os.getenv("VIDEOSIEVE_ASR_PROVIDER", "baseline").strip().lower()
    if provider == "funasr_local":
        model = os.getenv("VIDEOSIEVE_ASR_MODEL", "FunAudioLLM/Fun-ASR-Nano-2512").strip()
        hub = os.getenv("VIDEOSIEVE_ASR_HUB", "ms").strip().lower()
        device = os.getenv("VIDEOSIEVE_ASR_DEVICE", "auto").strip().lower()
        language = os.getenv("VIDEOSIEVE_ASR_LANGUAGE")
        return FunASRLocalProvider(
            model=model,
            hub=hub,
            device=device,
            language=language.strip() if isinstance(language, str) and language.strip() else None,
        )
    return BaselineASRProvider()
