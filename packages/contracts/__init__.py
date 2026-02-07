"""Shared data-contract package for VideoSieve."""

from .models import (
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

__all__ = [
    "__version__",
    "ControlCommand",
    "ControlCommandType",
    "EventEnvelope",
    "EventType",
    "Job",
    "JobStatus",
    "Project",
    "ProjectStatus",
    "SourceType",
    "StageName",
    "StageState",
    "StageStatus",
]

__version__ = "0.1.0"
