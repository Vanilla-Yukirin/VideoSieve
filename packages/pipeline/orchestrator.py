"""Stage orchestration with cooperative control semantics."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from asr import ASRProvider, BaselineASRProvider, write_transcript_jsonl
from contracts import ControlCommandType, JobStatus, StageName
from core import apply_job_transition
from deliverables import DeliverablesService
from fusion import FusionService
from hotwords import run_hotwords_from_meta
from infra import EventBus, JobRepository, WorkspaceStore
from ingest import IngestRequest, run_local_ingest
from keyframes import KeyframeBaselineService
from ocr import MockOCRProvider, OCRBaselineService

from .checkpoint import CheckpointStore
from .control import ControlAckPayload, evaluate_control_command
from .events import publish_event
from .models import STAGE_SEQUENCE, STAGE_WEIGHTS, PipelineRunResult


@dataclass(slots=True)
class _SafetySignal(Exception):
    kind: str


class PipelineOrchestrator:
    """Run one job through the canonical stage sequence."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        workspace: WorkspaceStore,
        event_bus: EventBus,
        asr_provider: ASRProvider | None = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._asr_provider = asr_provider or BaselineASRProvider()
        self._checkpoint_store = CheckpointStore(workspace)
        self._pending_pause: set[str] = set()
        self._pending_cancel: set[str] = set()
        self._pending_delete: set[str] = set()

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
        """Run or rerun one job with checkpoint support."""

        self._workspace.ensure_project_layout(project_id)
        checkpoint = self._checkpoint_store.load(project_id, job_id)
        checkpoint.reused_until_stage = None

        current_status = _to_job_status(self._job_status(job_id))
        if current_status in {JobStatus.QUEUED, JobStatus.PAUSED}:
            self._set_job_status(project_id, job_id, JobStatus.RUNNING, stage=None)

        start_index = 0
        if rerun_from_stage is not None:
            start_index = STAGE_SEQUENCE.index(rerun_from_stage)
            if start_index > 0:
                checkpoint.reused_until_stage = STAGE_SEQUENCE[start_index - 1].value

        completed = list(checkpoint.completed_stages)

        try:
            for index, stage in enumerate(STAGE_SEQUENCE):
                self._safety_point(project_id, job_id)

                if index < start_index:
                    continue

                checkpoint.current_stage = stage.value
                self._checkpoint_store.save(checkpoint)
                self._publish_stage_changed(project_id, job_id, stage)
                self._set_job_status(project_id, job_id, JobStatus.RUNNING, stage=stage)

                try:
                    self._run_stage(
                        stage,
                        project_id=project_id,
                        job_id=job_id,
                        source_path=source_path,
                        title=title,
                        description=description,
                        tags=tags or [],
                        language_hint=language_hint,
                        duration_seconds=duration_seconds,
                    )
                except Exception:
                    checkpoint.stage_statuses[stage.value] = "failed"
                    self._checkpoint_store.save(checkpoint)
                    self._set_job_status(project_id, job_id, JobStatus.FAILED, stage=stage)
                    raise

                checkpoint.stage_statuses[stage.value] = "succeeded"
                if stage.value not in completed:
                    completed.append(stage.value)
                checkpoint.completed_stages = completed
                self._checkpoint_store.save(checkpoint)
                self._publish_progress(project_id, job_id, stage)

                self._safety_point(project_id, job_id)

            checkpoint.current_stage = None
            self._checkpoint_store.save(checkpoint)
            self._set_job_status(
                project_id, job_id, JobStatus.SUCCEEDED, stage=StageName.DELIVERABLES
            )
            return PipelineRunResult(
                project_id=project_id,
                job_id=job_id,
                status=JobStatus.SUCCEEDED.value,
                completed_stages=completed,
                reused_until_stage=checkpoint.reused_until_stage,
            )
        except _SafetySignal as signal:
            if signal.kind == JobStatus.CANCELLED.value:
                checkpoint.current_stage = None
                self._checkpoint_store.save(checkpoint)
                self._set_job_status(project_id, job_id, JobStatus.CANCELLED, stage=None)
                if job_id in self._pending_delete:
                    self._cleanup_project_workspace(project_id)
                    self._pending_delete.discard(job_id)
                return PipelineRunResult(
                    project_id=project_id,
                    job_id=job_id,
                    status=JobStatus.CANCELLED.value,
                    completed_stages=completed,
                    reused_until_stage=checkpoint.reused_until_stage,
                )

            self._set_job_status(
                project_id,
                job_id,
                JobStatus.PAUSED,
                stage=StageName(checkpoint.current_stage) if checkpoint.current_stage else None,
            )
            return PipelineRunResult(
                project_id=project_id,
                job_id=job_id,
                status=JobStatus.PAUSED.value,
                completed_stages=completed,
                reused_until_stage=checkpoint.reused_until_stage,
            )

    def handle_control_command(
        self,
        *,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        """Evaluate one control command and publish ``control_ack``."""

        current = _to_job_status(self._job_status(job_id))
        decision = evaluate_control_command(command, current)

        if decision.request_cancel:
            self._pending_cancel.add(job_id)
        if (
            command is ControlCommandType.PAUSE
            and decision.accepted
            and decision.target_status is not None
        ):
            self._pending_pause.add(job_id)
        if command is ControlCommandType.DELETE:
            self._pending_delete.add(job_id)
            if decision.request_cleanup:
                self._cleanup_project_workspace(project_id)
                self._pending_delete.discard(job_id)

        if command is ControlCommandType.RESUME and decision.accepted and decision.target_status:
            self._pending_pause.discard(job_id)
            self._set_job_status(project_id, job_id, decision.target_status, stage=None)

        payload = ControlAckPayload(
            command=command.value,
            accepted=decision.accepted,
            reason=decision.reason,
            code=decision.code,
        ).to_dict()
        ack_payload: dict[str, object] = dict(payload)
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="control_ack",
            payload=ack_payload,
        )
        return payload

    def _safety_point(self, project_id: str, job_id: str) -> None:
        current = _to_job_status(self._job_status(job_id))

        if job_id in self._pending_cancel and current in {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.PAUSED,
        }:
            self._set_job_status(project_id, job_id, JobStatus.CANCELLED, stage=None)
            self._pending_cancel.discard(job_id)
            raise _SafetySignal(JobStatus.CANCELLED.value)

        if job_id in self._pending_pause and current is JobStatus.RUNNING:
            self._pending_pause.discard(job_id)
            raise _SafetySignal(JobStatus.PAUSED.value)

    def _run_stage(
        self,
        stage: StageName,
        *,
        project_id: str,
        job_id: str,
        source_path: str,
        title: str | None,
        description: str,
        tags: list[str],
        language_hint: str | None,
        duration_seconds: float,
    ) -> None:
        if stage is StageName.INGEST:
            run_local_ingest(
                self._workspace,
                IngestRequest(
                    project_id=project_id,
                    job_id=job_id,
                    source_path=source_path,
                    title=title,
                    description=description,
                    tags=tags,
                    language_hint=language_hint,
                ),
            )
            return

        if stage is StageName.HOTWORDS:
            run_hotwords_from_meta(self._workspace, project_id=project_id, job_id=job_id)
            return

        if stage is StageName.ASR:
            audio_path = self._workspace.path(project_id, "media", "audio.wav")
            if not audio_path.exists():
                audio_path = self._workspace.source_video_file(project_id)
            write_transcript_jsonl(
                self._asr_provider,
                audio_path=audio_path,
                output_path=self._workspace.path(project_id, "asr", "transcript.jsonl"),
                language_hint=language_hint,
            )
            return

        if stage is StageName.KEYFRAMES:
            KeyframeBaselineService(self._workspace).run(
                project_id,
                duration_seconds=duration_seconds,
                interval_seconds=5.0,
                reason="sample",
            )
            return

        if stage is StageName.OCR:
            OCRBaselineService(self._workspace, provider=MockOCRProvider()).run(
                project_id,
                language_hint=language_hint,
            )
            return

        if stage is StageName.FUSION:
            FusionService(self._workspace).run(project_id, job_id=job_id)
            return

        if stage is StageName.DELIVERABLES:
            DeliverablesService(self._workspace).run(project_id, job_id=job_id)
            return

        raise ValueError(f"unsupported stage: {stage.value}")

    def _publish_stage_changed(self, project_id: str, job_id: str, stage: StageName) -> None:
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="stage_changed",
            payload={"to": stage.value},
        )

    def _publish_progress(self, project_id: str, job_id: str, stage: StageName) -> None:
        stage_index = STAGE_SEQUENCE.index(stage)
        pct = sum(STAGE_WEIGHTS[item] for item in STAGE_SEQUENCE[: stage_index + 1])
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="progress",
            payload={"stage": stage.value, "pct": min(100.0, pct)},
        )

    def _cleanup_project_workspace(self, project_id: str) -> None:
        root = self._workspace.project_root(project_id)
        if root.exists():
            shutil.rmtree(root)

    def _job_status(self, job_id: str) -> str:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        return job.status

    def _set_job_status(
        self,
        project_id: str,
        job_id: str,
        target: JobStatus,
        *,
        stage: StageName | None,
    ) -> None:
        current = _to_job_status(self._job_status(job_id))
        if current is not target:
            apply_job_transition(current, target)
        self._repository.update_job_status(
            job_id,
            status=target.value,
            stage=stage.value if stage is not None else None,
        )
        self._repository.update_project_status(project_id, target.value)


def _to_job_status(value: str) -> JobStatus:
    return JobStatus(value)
