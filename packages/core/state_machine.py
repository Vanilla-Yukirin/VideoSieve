"""State transition validators for job and stage lifecycles."""

from __future__ import annotations

from contracts import JobStatus, StageStatus

from .errors import InvalidStateTransitionError


_ALLOWED_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.PAUSED,
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    },
    JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}

_ALLOWED_STAGE_TRANSITIONS: dict[StageStatus, set[StageStatus]] = {
    StageStatus.PENDING: {StageStatus.RUNNING},
    StageStatus.RUNNING: {StageStatus.SUCCEEDED, StageStatus.FAILED, StageStatus.SKIPPED},
    StageStatus.SUCCEEDED: set(),
    StageStatus.FAILED: set(),
    StageStatus.SKIPPED: set(),
}


def validate_job_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate a job lifecycle transition and raise on invalid edges."""

    if target not in _ALLOWED_JOB_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"Invalid job state transition: {current.value} -> {target.value}.",
            context={"current": current.value, "target": target.value, "scope": "job"},
        )


def apply_job_transition(current: JobStatus, target: JobStatus) -> JobStatus:
    """Apply a validated job state transition."""

    validate_job_transition(current, target)
    return target


def validate_stage_transition(current: StageStatus, target: StageStatus) -> None:
    """Validate a stage lifecycle transition and raise on invalid edges."""

    if target not in _ALLOWED_STAGE_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"Invalid stage state transition: {current.value} -> {target.value}.",
            context={"current": current.value, "target": target.value, "scope": "stage"},
        )


def apply_stage_transition(current: StageStatus, target: StageStatus) -> StageStatus:
    """Apply a validated stage state transition."""

    validate_stage_transition(current, target)
    return target
