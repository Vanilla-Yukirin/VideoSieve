"""Pipeline constants and lightweight run metadata models."""

from __future__ import annotations

from dataclasses import dataclass

from contracts import StageName

STAGE_SEQUENCE: tuple[StageName, ...] = (
    StageName.INGEST,
    StageName.HOTWORDS,
    StageName.ASR,
    StageName.KEYFRAMES,
    StageName.FRAME_SUMMARY,
    StageName.FUSION,
    StageName.DELIVERABLES,
)

STAGE_WEIGHTS: dict[StageName, float] = {
    StageName.INGEST: 5.0,
    StageName.HOTWORDS: 5.0,
    StageName.ASR: 35.0,
    StageName.KEYFRAMES: 20.0,
    StageName.FRAME_SUMMARY: 15.0,
    StageName.FUSION: 10.0,
    StageName.DELIVERABLES: 10.0,
}


@dataclass(slots=True)
class PipelineRunResult:
    """Result metadata returned by one orchestrator run."""

    project_id: str
    job_id: str
    status: str
    completed_stages: list[str]
    reused_until_stage: str | None = None
