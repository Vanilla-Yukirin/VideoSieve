"""Checkpoint persistence for rerun-from-stage and resume."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from contracts.models import SCHEMA_VERSION
from infra import WorkspaceStore


@dataclass(slots=True)
class PipelineCheckpoint:
    """Checkpoint payload stored under workspace meta directory."""

    project_id: str
    job_id: str
    current_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    stage_statuses: dict[str, str] = field(default_factory=dict)
    reused_until_stage: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_statuses": self.stage_statuses,
            "reused_until_stage": self.reused_until_stage,
        }


class CheckpointStore:
    """Read/write checkpoint files under ``meta/``."""

    def __init__(self, workspace: WorkspaceStore) -> None:
        self._workspace = workspace

    def path(self, project_id: str, job_id: str) -> str:
        return str(self._workspace.job_path(project_id, job_id, "meta", "pipeline.checkpoint.json"))

    def load(self, project_id: str, job_id: str) -> PipelineCheckpoint:
        checkpoint_path = self._workspace.job_path(
            project_id, job_id, "meta", "pipeline.checkpoint.json"
        )
        if not checkpoint_path.exists():
            return PipelineCheckpoint(project_id=project_id, job_id=job_id)

        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return PipelineCheckpoint(
            project_id=project_id,
            job_id=job_id,
            current_stage=_as_str_or_none(payload.get("current_stage")),
            completed_stages=[str(stage) for stage in payload.get("completed_stages", [])],
            stage_statuses={
                str(name): str(status)
                for name, status in dict(payload.get("stage_statuses", {})).items()
            },
            reused_until_stage=_as_str_or_none(payload.get("reused_until_stage")),
        )

    def save(self, checkpoint: PipelineCheckpoint) -> None:
        checkpoint_path = self._workspace.job_path(
            checkpoint.project_id,
            checkpoint.job_id,
            "meta",
            "pipeline.checkpoint.json",
        )
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _as_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
