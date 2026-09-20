"""Provider contracts for model-generated overall summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OverallSummaryProviderError(RuntimeError):
    """Structured provider failure that must not be presented as a summary."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class OverallSummaryResult:
    """One successful model response."""

    text: str
    provider: str
    model: str


@dataclass(frozen=True)
class SummaryProviderProvenance:
    """Non-secret provider configuration recorded with generated summaries."""

    provider: str
    model: str
    prompt_version: str | None
    prompt_sha256: str | None
    endpoint_sha256: str | None
    parameters: dict[str, object]


class OverallSummaryProvider(Protocol):
    """Model adapter used by the hierarchical summary service."""

    @property
    def provider_name(self) -> str:
        """Return a stable provider identifier."""

    @property
    def model_name(self) -> str:
        """Return the configured model identifier."""

    def summarize(
        self,
        source_text: str,
        *,
        language_hint: str | None,
        partial: bool,
    ) -> OverallSummaryResult:
        """Summarize all supplied evidence or a partition of it."""

    def describe_provenance(
        self, *, language_hint: str | None
    ) -> SummaryProviderProvenance:
        """Return non-secret configuration used for this summary."""
