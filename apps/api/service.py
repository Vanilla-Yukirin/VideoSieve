"""Job-scoped API control plane service."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

from contracts import ControlCommandType, JobStatus
from infra import EventBus, EventSubscription, InfraEvent, JobRepository, WorkspaceStore
from ingest import IngestRequest, probe_url_formats
from pipeline.control import ControlAckPayload, evaluate_control_command

from .models import (
    ArtifactItem,
    IngestFormatItem,
    IngestProbeRequest,
    IngestProbeResponse,
    JobCreateRequest,
    JobSnapshot,
    ProjectCreateRequest,
)

MAX_LOG_BUFFER = 100


class ApiControlPlane:
    """REST-facing service for project/job control and snapshots."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        workspace: WorkspaceStore,
        event_bus: EventBus,
        control_dispatcher: (
            Callable[[str, str, ControlCommandType], dict[str, str | bool]] | None
        ) = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._control_dispatcher = control_dispatcher or self._default_control_dispatcher
        self._subscriptions: dict[str, EventSubscription] = {}
        self._latest_progress: dict[str, float] = {}
        self._latest_stage: dict[str, str | None] = {}
        self._latest_logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_LOG_BUFFER))

    def create_project(self, payload: ProjectCreateRequest) -> str:
        """Create one project and its workspace."""

        project_id = f"p_{uuid.uuid4().hex[:12]}"
        self._repository.upsert_project(
            project_id, title=payload.title, status=JobStatus.QUEUED.value
        )
        self._workspace.ensure_project_layout(project_id)
        return project_id

    def get_project(self, project_id: str) -> dict[str, str | None] | None:
        """Get one project by id."""

        project = self._repository.get_project(project_id)
        if project is None:
            return None
        return {
            "project_id": project.project_id,
            "title": project.title,
            "status": project.status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }

    def create_job(self, payload: JobCreateRequest) -> str:
        """Create one queued job under one project."""

        project = self._repository.get_project(payload.project_id)
        if project is None:
            raise KeyError(f"project not found: {payload.project_id}")

        job_id = f"j_{uuid.uuid4().hex[:12]}"
        self._repository.create_job(
            job_id, payload.project_id, status=JobStatus.QUEUED.value, stage=None
        )
        self._workspace.ensure_project_layout(payload.project_id)
        config_path = self._workspace.path(payload.project_id, "meta", "config.snapshot.json")

        config: dict[str, object] = {
            "schema_version": "1.0",
            "project_id": payload.project_id,
            "job_id": job_id,
        }
        if payload.ingest:
            config["ingest"] = payload.ingest.model_dump(mode="json", exclude_none=True)

        config_path.write_text(
            json.dumps(
                config,
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        return job_id

    def probe_ingest_formats(self, payload: IngestProbeRequest) -> IngestProbeResponse:
        """Probe URL and return selectable quality options for frontend."""

        request = IngestRequest(
            project_id="p_probe",
            job_id="j_probe",
            source_url=payload.source_url,
            cookie_content=payload.cookie_content,
            cookie_file_path=payload.cookie_file_path,
            ytdlp_sort=payload.ytdlp_sort,
        )
        result = probe_url_formats(request)
        return IngestProbeResponse(
            source_url=result.source_url,
            title=result.title,
            uploader=result.uploader,
            duration_seconds=result.duration_seconds,
            webpage_url=result.webpage_url,
            formats=[IngestFormatItem.model_validate(item.model_dump()) for item in result.formats],
        )

    def get_job(self, job_id: str) -> dict[str, str | None] | None:
        """Get one job by id."""

        job = self._repository.get_job(job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "status": job.status,
            "stage": job.stage,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    def list_jobs_for_project(self, project_id: str) -> list[dict[str, str | None]]:
        """List jobs under one project."""

        jobs = self._repository.list_jobs_for_project(project_id)
        return [
            {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "status": job.status,
                "stage": job.stage,
                "error_code": job.error_code,
                "error_message": job.error_message,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
            for job in jobs
        ]

    def ensure_job_tracking(self, job_id: str) -> None:
        """Subscribe once to job event channel and maintain cache."""

        if job_id in self._subscriptions:
            return

        def _handler(event: InfraEvent) -> None:
            self._consume_event(event)

        self._subscriptions[job_id] = self._event_bus.subscribe(f"jobs:{job_id}", _handler)

    def release_job_tracking(self, job_id: str) -> None:
        """Drop one job subscription."""

        subscription = self._subscriptions.pop(job_id, None)
        if subscription is not None:
            subscription.unsubscribe()

    def list_artifacts(self, project_id: str) -> list[ArtifactItem]:
        """List workspace artifacts for one project."""

        root = self._workspace.project_root(project_id)
        if not root.exists():
            return []

        items: list[ArtifactItem] = []
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()
        ):
            relative = path.relative_to(root).as_posix()
            items.append(ArtifactItem(path=relative, size_bytes=path.stat().st_size))
        return items

    def get_job_snapshot(self, job_id: str) -> JobSnapshot:
        """Build one HTTP snapshot for UI convergence."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")

        self.ensure_job_tracking(job_id)
        progress = self._coalesce_progress(job_id, job.status)
        stage = self._latest_stage.get(job_id) or job.stage
        logs = self._latest_logs.get(job_id)

        return JobSnapshot(
            project_id=job.project_id,
            job_id=job_id,
            status=job.status,
            current_stage=stage,
            progress=progress,
            latest_logs=list(logs or []),
            artifacts=self.list_artifacts(job.project_id),
        )

    def dispatch_control_command(
        self,
        *,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        """Dispatch one job-scoped control command."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return self._control_dispatcher(job.project_id, job_id, command)

    def _consume_event(self, event: InfraEvent) -> None:
        if event.event_type == "progress":
            pct = float(event.payload.get("pct", 0.0))
            self._latest_progress[event.job_id] = max(0.0, min(100.0, pct))
            stage = event.payload.get("stage")
            if isinstance(stage, str):
                self._latest_stage[event.job_id] = stage
            return

        if event.event_type == "stage_changed":
            stage = event.payload.get("to")
            if isinstance(stage, str):
                self._latest_stage[event.job_id] = stage
            return

        if event.event_type == "log":
            message = event.payload.get("message")
            level = event.payload.get("level")
            if isinstance(message, str):
                prefix = f"[{level}] " if isinstance(level, str) else ""
                self._latest_logs[event.job_id].append(f"{prefix}{message}")

    def _coalesce_progress(self, job_id: str, status: str) -> float:
        if job_id in self._latest_progress:
            return self._latest_progress[job_id]
        if status == JobStatus.SUCCEEDED.value:
            return 100.0
        return 0.0

    def _default_control_dispatcher(
        self,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        current = self._repository.get_job(job_id)
        if current is None:
            raise KeyError(f"job not found: {job_id}")

        decision = evaluate_control_command(command, JobStatus(current.status))

        if decision.target_status is not None:
            self._repository.update_job_status(
                job_id, status=decision.target_status.value, stage=None
            )
            self._repository.update_project_status(project_id, decision.target_status.value)

        if command is ControlCommandType.DELETE and decision.request_cleanup:
            root = self._workspace.project_root(project_id)
            if root.exists():
                for child in sorted(
                    root.glob("**/*"), key=lambda item: len(item.parts), reverse=True
                ):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                root.rmdir()

        ack_payload: dict[str, str | bool] = ControlAckPayload(
            command=command.value,
            accepted=decision.accepted,
            reason=decision.reason,
            code=decision.code,
        ).to_dict()
        return ack_payload
