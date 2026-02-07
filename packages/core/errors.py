"""Core exception hierarchy with structured metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from .error_codes import INVALID_STATE_TRANSITION


@dataclass(slots=True)
class VideoSieveError(Exception):
    """Base domain error with stable error code."""

    code: str
    message: str
    hint: str | None = None
    retryable: bool = False
    context: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class InvalidStateTransitionError(VideoSieveError):
    """Raised when a state machine transition is illegal."""

    def __init__(self, message: str, *, context: dict[str, str] | None = None) -> None:
        super().__init__(
            code=INVALID_STATE_TRANSITION,
            message=message,
            hint="Check current/target state against allowed transition map.",
            retryable=False,
            context=context or {},
        )
