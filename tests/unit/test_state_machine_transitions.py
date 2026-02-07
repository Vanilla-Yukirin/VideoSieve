from __future__ import annotations

import pytest

from contracts import JobStatus, StageStatus
from core import INVALID_STATE_TRANSITION
from core import apply_job_transition, apply_stage_transition
from core import validate_job_transition, validate_stage_transition
from core.errors import InvalidStateTransitionError


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.QUEUED, JobStatus.CANCELLED),
        (JobStatus.RUNNING, JobStatus.PAUSED),
        (JobStatus.RUNNING, JobStatus.SUCCEEDED),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.CANCELLED),
        (JobStatus.PAUSED, JobStatus.RUNNING),
        (JobStatus.PAUSED, JobStatus.CANCELLED),
    ],
)
def test_valid_job_transitions(current: JobStatus, target: JobStatus) -> None:
    validate_job_transition(current, target)
    assert apply_job_transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.QUEUED, JobStatus.PAUSED),
        (JobStatus.PAUSED, JobStatus.SUCCEEDED),
        (JobStatus.SUCCEEDED, JobStatus.RUNNING),
        (JobStatus.FAILED, JobStatus.CANCELLED),
        (JobStatus.CANCELLED, JobStatus.RUNNING),
    ],
)
def test_invalid_job_transitions_raise_invalid_state_error(
    current: JobStatus,
    target: JobStatus,
) -> None:
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_job_transition(current, target)

    assert exc_info.value.code == INVALID_STATE_TRANSITION
    assert exc_info.value.context["scope"] == "job"


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (StageStatus.PENDING, StageStatus.RUNNING),
        (StageStatus.RUNNING, StageStatus.SUCCEEDED),
        (StageStatus.RUNNING, StageStatus.FAILED),
        (StageStatus.RUNNING, StageStatus.SKIPPED),
    ],
)
def test_valid_stage_transitions(current: StageStatus, target: StageStatus) -> None:
    validate_stage_transition(current, target)
    assert apply_stage_transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (StageStatus.PENDING, StageStatus.SUCCEEDED),
        (StageStatus.SUCCEEDED, StageStatus.RUNNING),
        (StageStatus.FAILED, StageStatus.RUNNING),
        (StageStatus.SKIPPED, StageStatus.RUNNING),
    ],
)
def test_invalid_stage_transitions_raise_invalid_state_error(
    current: StageStatus,
    target: StageStatus,
) -> None:
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_stage_transition(current, target)

    assert exc_info.value.code == INVALID_STATE_TRANSITION
    assert exc_info.value.context["scope"] == "stage"
