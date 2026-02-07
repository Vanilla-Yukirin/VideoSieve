"""Minimal worker entrypoints without a hard Celery runtime dependency."""

from __future__ import annotations

from contracts import ControlCommandType, StageName
from pipeline import PipelineOrchestrator, PipelineRunResult


class WorkerRuntime:
    """Thin adapter that delegates execution to ``PipelineOrchestrator``."""

    def __init__(self, orchestrator: PipelineOrchestrator) -> None:
        self._orchestrator = orchestrator

    def run_job(
        self,
        *,
        project_id: str,
        job_id: str,
        source_path: str,
        rerun_from_stage: StageName | None = None,
        title: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        language_hint: str | None = None,
        duration_seconds: float = 30.0,
    ) -> PipelineRunResult:
        """Execute one job through the pipeline."""

        return self._orchestrator.run_job(
            project_id=project_id,
            job_id=job_id,
            source_path=source_path,
            rerun_from_stage=rerun_from_stage,
            title=title,
            description=description,
            tags=tags,
            language_hint=language_hint,
            duration_seconds=duration_seconds,
        )

    def handle_control(
        self,
        *,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        """Route one control command to the orchestrator."""

        return self._orchestrator.handle_control_command(
            project_id=project_id,
            job_id=job_id,
            command=command,
        )
