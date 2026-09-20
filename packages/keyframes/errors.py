"""Typed keyframe-stage failures exposed through the pipeline error envelope."""

from __future__ import annotations


class KeyframeStageError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.retryable = retryable
