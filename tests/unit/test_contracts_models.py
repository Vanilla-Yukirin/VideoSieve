from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from contracts import (
    ControlCommand,
    ControlCommandType,
    EventEnvelope,
    EventType,
    Job,
    JobStatus,
    Project,
    ProjectStatus,
    SourceType,
    StageName,
    StageState,
    StageStatus,
)


def test_project_and_job_keep_semantics_separate() -> None:
    created_at = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)

    project = Project(
        project_id="p_20260208_001",
        source_type=SourceType.BILIBILI_URL,
        source_ref="https://www.bilibili.com/video/BV123",
        title="Linear Algebra Lecture 01",
        status=ProjectStatus.RUNNING,
        created_at=created_at,
    )
    job = Job(
        job_id="j_20260208_001",
        project_id=project.project_id,
        config_snapshot_path="workspaces/p_20260208_001/meta/config.snapshot.json",
        status=JobStatus.RUNNING,
        started_at=created_at,
    )

    assert project.project_id == "p_20260208_001"
    assert job.project_id == project.project_id
    assert job.job_id.startswith("j_")


def test_project_rejects_job_only_fields() -> None:
    with pytest.raises(ValidationError):
        Project.model_validate(
            {
                "project_id": "p_1",
                "source_type": SourceType.LOCAL_FILE,
                "source_ref": "C:/videos/lecture.mp4",
                "title": "Lecture",
                "status": ProjectStatus.QUEUED,
                "created_at": datetime(2026, 2, 8, 10, 0, tzinfo=UTC),
                "job_id": "j_1",
            }
        )


def test_stage_state_event_envelope_and_command_models() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)

    stage_state = StageState(
        project_id="p_1",
        job_id="j_1",
        stage=StageName.ASR,
        status=StageStatus.RUNNING,
        pct=35.5,
        updated_at=now,
    )
    event = EventEnvelope(
        event_type=EventType.PROGRESS,
        project_id="p_1",
        job_id="j_1",
        ts=now,
        payload={"stage": "asr", "pct": 35.5},
    )
    command = ControlCommand(
        command=ControlCommandType.PAUSE,
        project_id="p_1",
        job_id="j_1",
        issued_at=now,
    )

    assert stage_state.stage is StageName.ASR
    assert event.event_type is EventType.PROGRESS
    assert command.command is ControlCommandType.PAUSE
