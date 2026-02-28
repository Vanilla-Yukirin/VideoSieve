"""Command semantics aligned with the job state machine matrix."""

from __future__ import annotations

from dataclasses import dataclass

from contracts import ControlCommandType, JobStatus
from core import ALREADY_IN_TARGET_STATE, DELETE_PENDING_CLEANUP, INVALID_STATE_TRANSITION


@dataclass(slots=True)
class ControlDecision:
    """Decision output for one control command evaluation."""

    command: ControlCommandType
    accepted: bool
    code: str | None = None
    reason: str | None = None
    target_status: JobStatus | None = None
    request_cancel: bool = False
    request_cleanup: bool = False


@dataclass(slots=True)
class ControlAckPayload:
    """Fixed-shape control acknowledgement payload."""

    command: str
    accepted: bool
    reason: str | None = None
    code: str | None = None

    def to_dict(self) -> dict[str, str | bool]:
        payload: dict[str, str | bool] = {
            "command": self.command,
            "accepted": self.accepted,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.code is not None:
            payload["code"] = self.code
        return payload


def evaluate_control_command(command: ControlCommandType, current: JobStatus) -> ControlDecision:
    """Apply command x state matrix and return an explicit decision."""

    if command is ControlCommandType.PAUSE:
        if current is JobStatus.RUNNING:
            return ControlDecision(command=command, accepted=True, target_status=JobStatus.PAUSED)
        if current in {
            JobStatus.QUEUED,
            JobStatus.PAUSED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            return ControlDecision(
                command=command,
                accepted=True,
                code=ALREADY_IN_TARGET_STATE,
                reason="pause is a no-op in current state",
            )

    if command is ControlCommandType.RESUME:
        if current is JobStatus.PAUSED:
            return ControlDecision(command=command, accepted=True, target_status=JobStatus.RUNNING)
        if current is JobStatus.QUEUED:
            return ControlDecision(
                command=command,
                accepted=False,
                code=INVALID_STATE_TRANSITION,
                reason="resume only valid while paused",
            )
        return ControlDecision(
            command=command,
            accepted=True,
            code=ALREADY_IN_TARGET_STATE,
            reason="resume is a no-op in current state",
        )

    if command is ControlCommandType.CANCEL:
        if current in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSED}:
            return ControlDecision(
                command=command,
                accepted=True,
                target_status=JobStatus.CANCEL_REQUESTED,
                request_cancel=True,
            )
        if current is JobStatus.CANCEL_REQUESTED:
            return ControlDecision(
                command=command,
                accepted=True,
                code=ALREADY_IN_TARGET_STATE,
                reason="cancel is already requested",
            )
        return ControlDecision(
            command=command,
            accepted=True,
            code=ALREADY_IN_TARGET_STATE,
            reason="cancel is a no-op for terminal jobs",
        )

    if command is ControlCommandType.DELETE:
        if current in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return ControlDecision(
                command=command,
                accepted=True,
                request_cleanup=True,
            )
        if current is JobStatus.CANCEL_REQUESTED:
            return ControlDecision(
                command=command,
                accepted=True,
                code=DELETE_PENDING_CLEANUP,
                reason="delete accepted, waiting for terminal state before cleanup",
            )
        return ControlDecision(
            command=command,
            accepted=True,
            code=DELETE_PENDING_CLEANUP,
            reason="delete accepted, waiting for terminal state before cleanup",
            target_status=JobStatus.CANCEL_REQUESTED,
            request_cancel=True,
        )

    return ControlDecision(
        command=command,
        accepted=False,
        code=INVALID_STATE_TRANSITION,
        reason="unknown control command",
    )
