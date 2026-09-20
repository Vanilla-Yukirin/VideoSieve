"""Abstract interfaces for ASR providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ASRRequest, ASRResult


class ASRProviderError(RuntimeError):
    """Actionable external-provider failure preserved by the pipeline."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "Check the external ASR endpoint and retry the job.",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.retryable = retryable


class ASRProvider(ABC):
    """Provider contract for speech-to-text adapters."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return adapter identifier for observability and routing."""

    @abstractmethod
    def transcribe(self, request: ASRRequest) -> ASRResult:
        """Transcribe one normalized audio input into timestamped segments."""
