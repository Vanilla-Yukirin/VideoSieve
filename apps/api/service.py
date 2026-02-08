"""Job-scoped API control plane service."""

from __future__ import annotations

import json
import threading
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

from workers import WorkerRuntime

from contracts import ControlCommandType, JobStatus
from infra import (
    EventBus,
    EventSubscription,
    FileSystemWorkspaceStore,
    InfraEvent,
    JobRepository,
    SQLiteJobRepository,
    WorkspaceStore,
)
from ingest import IngestRequest, probe_url_formats
from pipeline import PipelineOrchestrator
from pipeline.control import ControlAckPayload, evaluate_control_command
from pipeline.dispatch import (
    PIPELINE_DISPATCH_FAILED,
    extract_ingest_config,
    load_job_config_snapshot,
)

from .models import (
    ArtifactItem,
    IngestAssetSelection,
    IngestFormatItem,
    IngestParams,
    IngestProbeRequest,
    IngestProbeResponse,
    JobCreateRequest,
    JobSnapshot,
    ProjectCreateRequest,
)

MAX_LOG_BUFFER = 100


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


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
        job_dispatcher: Callable[[str, str], None] | None = None,
        worker_runtime: WorkerRuntime | None = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._control_dispatcher = control_dispatcher or self._default_control_dispatcher
        self._worker_runtime = worker_runtime or WorkerRuntime(
            PipelineOrchestrator(
                repository=repository,
                workspace=workspace,
                event_bus=event_bus,
            )
        )
        self._job_dispatcher = job_dispatcher or self._default_job_dispatcher
        self._subscriptions: dict[str, EventSubscription] = {}
        self._latest_progress: dict[str, float] = {}
        self._latest_stage: dict[str, str | None] = {}
        self._latest_logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_LOG_BUFFER))
        self._dispatch_lock = threading.Lock()
        self._dispatched_jobs: set[str] = set()

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
        if payload.summary_enabled is not None:
            config["summary_enabled"] = payload.summary_enabled
        if payload.ingest:
            normalized_ingest, dedupe_estimate = self._normalize_ingest(payload.ingest)
            config["ingest"] = normalized_ingest
            config["dedupe_applied_estimate"] = dedupe_estimate

        config_path.write_text(
            json.dumps(
                config,
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._dispatch_job_if_needed(payload.project_id, job_id)
        return job_id

    def _dispatch_job_if_needed(self, project_id: str, job_id: str) -> None:
        with self._dispatch_lock:
            if job_id in self._dispatched_jobs:
                return
            self._dispatched_jobs.add(job_id)

        try:
            self._job_dispatcher(project_id, job_id)
        except Exception as exc:  # pragma: no cover - thread start failures are rare
            with self._dispatch_lock:
                self._dispatched_jobs.discard(job_id)
            self._mark_dispatch_failure(project_id, job_id, exc)

    def _default_job_dispatcher(self, project_id: str, job_id: str) -> None:
        def _runner() -> None:
            thread_repo: SQLiteJobRepository | None = None
            try:
                thread_repo = self._open_thread_safe_repository()
                thread_workspace = self._open_thread_safe_workspace()
                worker_runtime = WorkerRuntime(
                    PipelineOrchestrator(
                        repository=thread_repo,
                        workspace=thread_workspace,
                        event_bus=self._event_bus,
                    )
                )
                config_snapshot = load_job_config_snapshot(
                    thread_workspace,
                    project_id=project_id,
                )
                ingest_config = extract_ingest_config(config_snapshot)
                worker_runtime.run_job(
                    project_id=project_id,
                    job_id=job_id,
                    source_path=None,
                    ingest_config=ingest_config,
                    title=_as_optional_str(config_snapshot.get("title")),
                    description=_as_optional_str(config_snapshot.get("description")) or "",
                    tags=_as_str_list(config_snapshot.get("tags")),
                    language_hint=_as_optional_str(config_snapshot.get("language_hint")),
                )
            except Exception as exc:
                self._mark_dispatch_failure(project_id, job_id, exc)
            finally:
                if thread_repo is not None:
                    thread_repo.close()
                with self._dispatch_lock:
                    self._dispatched_jobs.discard(job_id)

        threading.Thread(target=_runner, name=f"pipeline-dispatch-{job_id}", daemon=True).start()

    def _mark_dispatch_failure(self, project_id: str, job_id: str, error: Exception) -> None:
        message = str(error) or error.__class__.__name__
        repository = self._open_thread_safe_repository()
        repository.update_job_status(
            job_id,
            status=JobStatus.FAILED.value,
            stage=None,
            error_code=PIPELINE_DISPATCH_FAILED,
            error_message=message,
        )
        repository.update_project_status(project_id, JobStatus.FAILED.value)
        repository.close()
        self._latest_logs[job_id].append(f"[error] dispatch failed: {message}")
        self._event_bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="log",
                project_id=project_id,
                job_id=job_id,
                payload={"level": "error", "message": f"dispatch failed: {message}"},
            ),
        )
        self._event_bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="error",
                project_id=project_id,
                job_id=job_id,
                payload={
                    "stage": "dispatch",
                    "code": PIPELINE_DISPATCH_FAILED,
                    "message": message,
                },
            ),
        )

    def _open_thread_safe_repository(self) -> SQLiteJobRepository:
        db_path = getattr(self._repository, "_db_path", None)
        if db_path is None:
            raise RuntimeError("thread dispatch requires sqlite repository")
        repository = SQLiteJobRepository(db_path)
        repository.ensure_schema()
        return repository

    def _open_thread_safe_workspace(self) -> FileSystemWorkspaceStore:
        base_dir = getattr(self._workspace, "_base_dir", None)
        if base_dir is None:
            raise RuntimeError("thread dispatch requires filesystem workspace")
        return FileSystemWorkspaceStore(base_dir)

    def _normalize_ingest(self, ingest: IngestParams) -> tuple[dict[str, object], bool]:
        analysis_asset = ingest.analysis_asset
        quality_asset = ingest.quality_asset

        if analysis_asset is None and quality_asset is None and ingest.video_format_id is not None:
            legacy = IngestAssetSelection(
                video_format_id=ingest.video_format_id,
                audio_format_id=ingest.audio_format_id,
            )
            analysis_asset = legacy
            quality_asset = legacy

        if analysis_asset is None and quality_asset is not None:
            analysis_asset = quality_asset
        if quality_asset is None and analysis_asset is not None:
            quality_asset = analysis_asset

        normalized: dict[str, object] = {}
        if ingest.source_url is not None:
            normalized["source_url"] = ingest.source_url
        if ingest.cookie_file_path is not None:
            normalized["cookie_file_path"] = ingest.cookie_file_path
        if ingest.cookie_secret_ref is not None:
            normalized["cookie_secret_ref"] = ingest.cookie_secret_ref
        if analysis_asset is not None:
            normalized["analysis_asset"] = analysis_asset.model_dump(mode="json", exclude_none=True)
        if quality_asset is not None:
            normalized["quality_asset"] = quality_asset.model_dump(mode="json", exclude_none=True)

        analysis_pair = (
            analysis_asset.video_format_id if analysis_asset is not None else None,
            analysis_asset.audio_format_id if analysis_asset is not None else None,
        )
        quality_pair = (
            quality_asset.video_format_id if quality_asset is not None else None,
            quality_asset.audio_format_id if quality_asset is not None else None,
        )
        return normalized, analysis_pair == quality_pair

    def probe_ingest_formats(self, payload: IngestProbeRequest) -> IngestProbeResponse:
        """Probe URL and return selectable quality options for frontend."""

        request = IngestRequest(
            project_id="p_probe",
            job_id="j_probe",
            source_url=payload.source_url,
            cookie_file_path=payload.cookie_file_path,
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
