"""Core primitives: state machine and domain errors."""

from .error_codes import (
    ALREADY_IN_TARGET_STATE,
    CONTROL_CONFLICT,
    DELETE_PENDING_CLEANUP,
    INVALID_STATE_TRANSITION,
    JOB_NOT_ACTIVE,
)
from .errors import InvalidStateTransitionError, VideoSieveError
from .state_machine import (
    apply_job_transition,
    apply_stage_transition,
    validate_job_transition,
    validate_stage_transition,
)

__all__ = [
    "ALREADY_IN_TARGET_STATE",
    "CONTROL_CONFLICT",
    "DELETE_PENDING_CLEANUP",
    "INVALID_STATE_TRANSITION",
    "JOB_NOT_ACTIVE",
    "InvalidStateTransitionError",
    "VideoSieveError",
    "apply_job_transition",
    "apply_stage_transition",
    "validate_job_transition",
    "validate_stage_transition",
]
