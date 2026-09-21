from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import apps.api.service as api_service
import pytest
from apps.api.rest import (
    REST_ROUTES,
    control_job,
    create_cookie,
    create_job,
    create_project,
    delete_project,
    get_job_snapshot,
    get_system_settings,
    list_job_artifacts,
    list_project_jobs,
    patch_system_settings,
    probe_ingest_formats,
)
from apps.api.service import ApiControlPlane, ApiError
from pydantic import ValidationError

from contracts import ControlCommandType, JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, InMemoryEventBus, SQLiteJobRepository
from ingest import IngestFormatOption, IngestFormatProbeResult


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")


def _make_control_plane(
    tmp_path: Path,
) -> tuple[ApiControlPlane, SQLiteJobRepository, InMemoryEventBus]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = InMemoryEventBus()
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    return control_plane, repository, bus


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float = 3.0,
    interval_seconds: float = 0.05,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return predicate()


def _publish_ready_artifact(
    workspace: FileSystemWorkspaceStore,
    project_id: str,
    job_id: str,
    *,
    content: str = "ok",
) -> Path:
    artifact = workspace.clean_transcript_file(project_id, job_id)
    artifact.write_text(content, encoding="utf-8")
    data = artifact.read_bytes()
    workspace.deliverables_manifest_file(project_id, job_id).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "ready": True,
                "project_id": project_id,
                "job_id": job_id,
                "artifacts": [
                    {
                        "path": "outputs/clean_transcript.md",
                        "size_bytes": len(data),
                        "sha256": sha256(data).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return artifact


def test_rest_project_job_snapshot_and_artifact_list(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    repository.update_project_status(project_id, JobStatus.RUNNING.value)
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _publish_ready_artifact(workspace, project_id, job_id)

    # Prime one snapshot so the control plane starts event tracking for this job.
    get_job_snapshot(control_plane, job_id)

    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="log",
            project_id=project_id,
            job_id=job_id,
            payload={"level": "info", "message": "started"},
        ),
    )
    bus.publish(
        f"jobs:{job_id}",
        InfraEvent(
            event_type="progress",
            project_id=project_id,
            job_id=job_id,
            payload={"stage": "asr", "pct": 27.5},
        ),
    )

    ready_snapshot = _wait_until(
        lambda: (
            lambda snap: (
                (snap["current_stage"] is not None) or (snap["status"] != JobStatus.RUNNING.value)
            )
        )(get_job_snapshot(control_plane, job_id))
    )
    assert ready_snapshot

    snapshot = get_job_snapshot(control_plane, job_id)
    artifacts = list_job_artifacts(control_plane, job_id)

    assert "GET /jobs/{job_id}/snapshot" in REST_ROUTES
    assert snapshot["status"] == JobStatus.RUNNING.value
    assert snapshot["current_stage"] == "asr"
    assert snapshot["progress"] == 27.5
    assert snapshot["latest_logs"] == ["[info] started"]
    assert any(item["path"] == "outputs/clean_transcript.md" for item in artifacts)


def test_snapshot_restores_persisted_progress_and_error_after_api_restart(
    tmp_path: Path,
) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_progress(job_id, progress=62.5, stage="frame_summary")
    repository.update_job_status(
        job_id,
        status=JobStatus.FAILED.value,
        stage="frame_summary",
        error_code="FRAME_SUMMARY_PROVIDER_FAILED",
        error_message="provider unavailable",
    )

    restarted_repository = SQLiteJobRepository(tmp_path / "infra.db")
    restarted_repository.ensure_schema()
    restarted = ApiControlPlane(
        repository=restarted_repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=InMemoryEventBus(),
    )
    snapshot = restarted.get_job_snapshot(job_id)

    assert snapshot.progress == 62.5
    assert snapshot.current_stage == "frame_summary"
    assert snapshot.error_code == "FRAME_SUMMARY_PROVIDER_FAILED"
    assert snapshot.error_message == "provider unavailable"


def test_artifacts_hide_uncommitted_or_tampered_deliverables(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    artifact = workspace.clean_transcript_file(project_id, job_id)
    artifact.write_text("stale", encoding="utf-8")

    assert not any(
        item.path.startswith("outputs/")
        for item in control_plane.list_artifacts(project_id, job_id)
    )
    _publish_ready_artifact(workspace, project_id, job_id, content="ready")
    assert [
        item.path
        for item in control_plane.list_artifacts(project_id, job_id)
        if item.path.startswith("outputs/")
    ] == [
        "outputs/clean_transcript.md",
        "outputs/deliverables.ready.json",
    ]
    artifact.write_text("tampered", encoding="utf-8")
    assert not any(
        item.path.startswith("outputs/")
        for item in control_plane.list_artifacts(project_id, job_id)
    )


def test_delete_project_removes_workspace_and_metadata(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    first_job = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(first_job, status=JobStatus.SUCCEEDED.value, stage=None)

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    artifact = workspace.job_path(project_id, first_job, "outputs", "clean_transcript.md")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("ok", encoding="utf-8")

    payload = delete_project(control_plane, project_id, force_cancel_active=False)
    assert payload["deleted"] is True
    assert "DELETE /projects/{project_id}" in REST_ROUTES
    assert repository.get_project(project_id) is None
    assert repository.list_jobs_for_project(project_id) == []
    assert workspace.project_root(project_id).exists() is False


def test_delete_project_rejects_when_active_jobs_exist_without_force(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")

    with pytest.raises(ApiError) as exc_info:
        delete_project(control_plane, project_id, force_cancel_active=False)
    assert exc_info.value.code == "project_has_active_jobs"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details.get("active_job_ids") == [job_id]


def test_delete_project_force_cancel_active_jobs_then_delete(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")

    recorded: list[tuple[str, str]] = []
    original = control_plane.dispatch_control_command

    def _recording_dispatch(*, job_id: str, command: ControlCommandType) -> dict[str, str | bool]:
        recorded.append((job_id, str(command)))
        return original(job_id=job_id, command=command)

    control_plane.dispatch_control_command = _recording_dispatch  # type: ignore[method-assign]

    payload = delete_project(control_plane, project_id, force_cancel_active=True)
    assert payload["deleted"] is True
    assert payload["cancelled_job_ids"] == [job_id]
    assert recorded and recorded[0][0] == job_id
    assert "cancel" in recorded[0][1]
    assert repository.get_project(project_id) is None
    assert list_project_jobs(control_plane, project_id) == []


def test_delete_project_force_cancel_times_out_when_jobs_stay_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = InMemoryEventBus()

    def _noop_dispatch(
        _project_id: str, _job_id: str, _command: ControlCommandType
    ) -> dict[str, str | bool]:
        return {"command": "cancel", "accepted": True}

    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
        control_dispatcher=_noop_dispatch,
    )
    monkeypatch.setattr(api_service, "PROJECT_DELETE_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(api_service, "PROJECT_DELETE_POLL_SECONDS", 0.01)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")

    with pytest.raises(ApiError) as exc_info:
        delete_project(control_plane, project_id, force_cancel_active=True)
    assert exc_info.value.code == "project_delete_pending_cancel"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details.get("pending_job_ids") == [job_id]


def test_create_job_rejected_while_project_deletion_in_progress(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]

    with control_plane._project_delete_lock:  # type: ignore[attr-defined]
        control_plane._deleting_projects.add(project_id)  # type: ignore[attr-defined]

    with pytest.raises(ApiError) as exc_info:
        create_job(control_plane, {"project_id": project_id})
    assert exc_info.value.code == "project_delete_in_progress"
    assert exc_info.value.status_code == 409


def test_create_job_blocks_on_project_lock_and_sees_delete_marker(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(
        tmp_path,
    )
    project_id = "p_locktest"
    create_called = {"value": False}
    outcome: dict[str, str] = {}

    project_exists = {"value": True}
    control_plane._repository.get_project = (  # type: ignore[method-assign]
        lambda _project_id: object() if project_exists["value"] else None
    )

    def _fake_create_job(
        _job_id: str, _project_id: str, *, status: str, stage: str | None = None
    ) -> None:
        create_called["value"] = True

    control_plane._repository.create_job = _fake_create_job  # type: ignore[method-assign]
    control_plane._workspace.ensure_job_layout = lambda _project_id, _job_id: tmp_path  # type: ignore[method-assign]
    control_plane._workspace.config_snapshot_file = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: tmp_path / "config.snapshot.json"
    )

    from apps.api.models import JobCreateRequest

    project_lock = control_plane._get_project_lock(project_id)  # type: ignore[attr-defined]
    project_lock.acquire()
    worker_started = threading.Event()

    def _runner() -> None:
        worker_started.set()
        try:
            control_plane.create_job(JobCreateRequest(project_id=project_id))
            outcome["value"] = "created"
        except ApiError as exc:
            outcome["value"] = exc.code
        except Exception as exc:  # pragma: no cover - defensive
            outcome["value"] = exc.__class__.__name__

    thread = threading.Thread(target=_runner)
    thread.start()
    assert worker_started.wait(timeout=1.0)
    time.sleep(0.05)
    assert thread.is_alive()

    with control_plane._project_delete_lock:  # type: ignore[attr-defined]
        control_plane._deleting_projects.add(project_id)  # type: ignore[attr-defined]
    project_exists["value"] = True
    project_lock.release()

    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert outcome["value"] == "project_delete_in_progress"
    assert create_called["value"] is False


def test_delete_project_returns_error_when_workspace_cleanup_fails(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.SUCCEEDED.value, stage=None)

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    blocking_file = workspace.project_root(project_id) / "blocked"
    blocking_file.write_text("x", encoding="utf-8")
    control_plane._workspace.project_root = (  # type: ignore[method-assign]
        lambda _project_id: blocking_file
    )

    with pytest.raises(ApiError) as exc_info:
        delete_project(control_plane, project_id, force_cancel_active=False)
    assert exc_info.value.code == "project_delete_pending_cleanup"
    assert exc_info.value.status_code == 409
    assert repository.get_project(project_id) is not None


def test_job_snapshot_loads_persisted_worker_logs_after_restart(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    worker_log = workspace.worker_log_file(project_id, job_id)
    worker_log.parent.mkdir(parents=True, exist_ok=True)
    worker_log.write_text("[error] worker failed before restart\n", encoding="utf-8")

    restarted = ApiControlPlane(
        repository=repository,
        workspace=workspace,
        event_bus=bus,
    )
    snapshot = get_job_snapshot(restarted, job_id)
    assert "[error] worker failed before restart" in snapshot["latest_logs"]


def test_job_snapshot_merges_persisted_and_memory_logs_without_overlap_duplicates(
    tmp_path: Path,
) -> None:
    control_plane, _, bus = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    log_file = workspace.worker_log_file(project_id, job_id)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("[info] a\n[info] b\n[info] c\n", encoding="utf-8")

    get_job_snapshot(control_plane, job_id)
    for message in ("a", "b", "c"):
        bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="log",
                project_id=project_id,
                job_id=job_id,
                payload={"level": "info", "message": message},
            ),
        )

    snapshot = get_job_snapshot(control_plane, job_id)
    assert snapshot["latest_logs"] == ["[info] a", "[info] b", "[info] c"]


def test_rest_control_commands_are_job_scoped(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    for command in ("pause", "resume", "cancel", "delete"):
        ack = control_job(control_plane, job_id=job_id, command=command)
        assert ack["command"] == command
        assert "accepted" in ack

    job = repository.get_job(job_id)
    if job is not None:
        assert job.status in {
            JobStatus.QUEUED.value,
            JobStatus.PAUSED.value,
            JobStatus.RUNNING.value,
            JobStatus.CANCEL_REQUESTED.value,
            JobStatus.CANCELLED.value,
        }


def test_job_delete_returns_pending_cleanup_when_workspace_busy(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.CANCELLED.value, stage=None)

    control_plane._cleanup_job_workspace = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: False
    )

    ack = control_job(control_plane, job_id=job_id, command="delete")
    assert ack["accepted"] is True
    assert ack["code"] == "DELETE_PENDING_CLEANUP"
    assert repository.get_job(job_id) is not None


def test_job_delete_removes_job_row_after_cleanup(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.CANCELLED.value, stage=None)

    ack = control_job(control_plane, job_id=job_id, command="delete")
    assert ack["accepted"] is True
    assert repository.get_job(job_id) is None


def test_pending_job_delete_is_finalized_during_snapshot(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.CANCELLED.value, stage=None)

    control_plane._cleanup_job_workspace = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: False
    )
    ack = control_job(control_plane, job_id=job_id, command="delete")
    assert ack["code"] == "DELETE_PENDING_CLEANUP"

    control_plane._cleanup_job_workspace = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: True
    )

    with pytest.raises(KeyError):
        get_job_snapshot(control_plane, job_id)
    assert repository.get_job(job_id) is None


def test_pending_job_delete_survives_control_plane_restart(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(
        tmp_path,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    repository.update_job_status(job_id, status=JobStatus.CANCELLED.value, stage=None)

    control_plane._cleanup_job_workspace = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: False
    )
    ack = control_job(control_plane, job_id=job_id, command="delete")
    assert ack["code"] == "DELETE_PENDING_CLEANUP"

    restarted = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    restarted._cleanup_job_workspace = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: True
    )

    with pytest.raises(KeyError):
        get_job_snapshot(restarted, job_id)
    assert repository.get_job(job_id) is None


def test_rest_ingest_probe_route_returns_format_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    def _fake_probe_url_formats(_request: object) -> IngestFormatProbeResult:
        return IngestFormatProbeResult(
            source_url="https://www.bilibili.com/video/BV1demo",
            title="demo title",
            uploader="demo-up",
            duration_seconds=66.6,
            webpage_url="https://www.bilibili.com/video/BV1demo",
            formats=[
                IngestFormatOption(
                    format_id="30116",
                    resolution="1920x1080",
                    vcodec="avc1",
                    acodec="none",
                    is_video_only=True,
                    is_audio_only=False,
                )
            ],
        )

    monkeypatch.setattr(api_service, "probe_url_formats", _fake_probe_url_formats)

    payload = probe_ingest_formats(
        control_plane,
        {
            "source_url": "https://www.bilibili.com/video/BV1demo",
        },
    )
    assert "POST /ingest/probe" in REST_ROUTES
    assert payload["title"] == "demo title"
    formats = payload.get("formats")
    assert isinstance(formats, list)
    assert isinstance(formats[0], dict)
    assert formats[0]["format_id"] == "30116"
    assert "ext" in formats[0]
    assert "resolution" in formats[0]
    assert "fps" in formats[0]
    assert "tbr" in formats[0]
    assert "protocol" in formats[0]
    assert "vcodec" in formats[0]
    assert "acodec" in formats[0]
    assert "filesize_approx" in formats[0]
    assert "is_video_only" in formats[0]
    assert "is_audio_only" in formats[0]


def test_rest_ingest_probe_rejects_legacy_ytdlp_sort_field(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    with pytest.raises(ValidationError):
        probe_ingest_formats(
            control_plane,
            {
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "ytdlp_sort": "res,br",
            },
        )


def test_rest_ingest_probe_uses_cookie_id_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "probe-secret")
    control_plane, _, _ = _make_control_plane(tmp_path)
    cookie = create_cookie(
        control_plane,
        {
            "name": "bili",
            "cookie_netscape_text": (
                "# Netscape HTTP Cookie File\n"
                ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tvault_token\n"
            ),
        },
    )

    captured: dict[str, object] = {}

    def _fake_probe_url_formats(request: object) -> IngestFormatProbeResult:
        captured["cookie_content"] = getattr(request, "cookie_content", None)
        captured["cookie_file_path"] = getattr(request, "cookie_file_path", None)
        return IngestFormatProbeResult(
            source_url="https://www.bilibili.com/video/BV1demo",
            title="demo title",
            formats=[IngestFormatOption(format_id="30116")],
        )

    monkeypatch.setattr(api_service, "probe_url_formats", _fake_probe_url_formats)

    payload = probe_ingest_formats(
        control_plane,
        {
            "source_url": "https://www.bilibili.com/video/BV1demo",
            "cookie_id": str(cookie["id"]),
        },
    )
    assert payload["title"] == "demo title"
    assert captured["cookie_content"] is not None
    assert "vault_token" in str(captured["cookie_content"])
    assert captured["cookie_file_path"] is None


def test_rest_ingest_probe_prefers_cookie_id_over_cookie_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "probe-secret")
    control_plane, _, _ = _make_control_plane(tmp_path)
    cookie = create_cookie(
        control_plane,
        {
            "name": "bili",
            "cookie_netscape_text": (
                "# Netscape HTTP Cookie File\n"
                ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tprefer_vault\n"
            ),
        },
    )

    captured: dict[str, object] = {}

    def _fake_probe_url_formats(request: object) -> IngestFormatProbeResult:
        captured["cookie_content"] = getattr(request, "cookie_content", None)
        captured["cookie_file_path"] = getattr(request, "cookie_file_path", None)
        return IngestFormatProbeResult(
            source_url="https://www.bilibili.com/video/BV1demo",
            title="demo title",
            formats=[IngestFormatOption(format_id="30116")],
        )

    monkeypatch.setattr(api_service, "probe_url_formats", _fake_probe_url_formats)

    _ = probe_ingest_formats(
        control_plane,
        {
            "source_url": "https://www.bilibili.com/video/BV1demo",
            "cookie_id": str(cookie["id"]),
            "cookie_file_path": "/tmp/legacy.cookies.txt",
        },
    )
    assert "prefer_vault" in str(captured["cookie_content"])
    assert captured["cookie_file_path"] is None


def test_rest_ingest_probe_rejects_unknown_cookie_id(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    with pytest.raises(KeyError):
        probe_ingest_formats(
            control_plane,
            {
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "cookie_id": "c_missing",
            },
        )


def test_create_job_persists_ingest_format_selection_in_snapshot(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(
        control_plane,
        {
            "project_id": project_id,
            "summary_enabled": False,
            "ingest": {
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "analysis_asset": {
                    "video_format_id": "30032",
                    "audio_format_id": "30280",
                },
                "quality_asset": {
                    "video_format_id": "30116",
                    "audio_format_id": "30280",
                },
                "cookie_secret_ref": "secrets/bili/prod",
            },
        },
    )["job_id"]

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    snapshot_path = workspace.config_snapshot_file(project_id, job_id)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ingest = payload["ingest"]

    assert payload["job_id"] == job_id
    assert payload["summary_enabled"] is False
    assert payload["asr"] == {
        "provider": "unconfigured",
        "transport": "websocket",
        "endpoint": "",
        "language": "auto",
            "context": "",
            "timeout_seconds": 900,
            "credential_ref": None,
            "segment_seconds": 60.0,
            "overlap_seconds": 4.0,
        }
    assert payload["dedupe_applied_estimate"] is False
    assert ingest["source_url"] == "https://www.bilibili.com/video/BV1demo"
    assert ingest["analysis_asset"] == {"video_format_id": "30032", "audio_format_id": "30280"}
    assert ingest["quality_asset"] == {"video_format_id": "30116", "audio_format_id": "30280"}
    assert ingest["cookie_secret_ref"] == "secrets/bili/prod"


def test_create_job_backward_compatible_without_format_selection(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(
        control_plane,
        {
            "project_id": project_id,
            "ingest": {
                "source_url": "https://www.bilibili.com/video/BV1compat",
            },
        },
    )["job_id"]

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    snapshot_path = workspace.config_snapshot_file(project_id, job_id)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ingest = payload["ingest"]

    assert ingest["source_url"] == "https://www.bilibili.com/video/BV1compat"
    assert "video_format_id" not in ingest
    assert "audio_format_id" not in ingest


def test_create_job_stays_queued_until_independent_worker_claims(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]

    job_id = create_job(
        control_plane,
        {
            "project_id": project_id,
            "ingest": {
                "source_url": "https://www.bilibili.com/video/BV1dispatch",
                "analysis_asset": {"video_format_id": "30032", "audio_format_id": "30280"},
                "quality_asset": {"video_format_id": "30116", "audio_format_id": "30280"},
            },
        },
    )["job_id"]

    job = repository.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.QUEUED.value
    assert job.worker_id is None
    snapshot = get_job_snapshot(control_plane, job_id)
    assert snapshot["status"] == JobStatus.QUEUED.value
    assert snapshot["current_stage"] is None
    assert snapshot["progress"] == 0.0


def test_settings_are_available_without_authentication(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)

    assert "POST /projects/{project_id}/jobs/upload" in REST_ROUTES
    assert "GET /cookies" in REST_ROUTES
    assert "POST /cookies/{cookie_id}/validate" in REST_ROUTES
    assert not any(
        "/auth/" in route or "/guest/" in route or "/public/" in route
        for route in REST_ROUTES
    )

    settings = get_system_settings(control_plane)
    assert settings["asr_provider"] == "unconfigured"
    assert settings["asr_token_configured"] is False
    assert "guest_mode_enabled" not in settings
    assert "guest_allow_cookie_input" not in settings

    patched = patch_system_settings(
        control_plane,
        {"asr_language": "zh", "asr_context": "课程背景"},
    )
    assert patched["asr_language"] == "zh"
    assert repository.get_setting("asr_language") == '"zh"'
    logs = repository.list_recent_operation_logs(limit=5)
    assert logs[0].actor_type == "local"
    assert logs[0].actor_id == "local"


def test_settings_persists_capswriter_without_requiring_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CAPSWRITER_TOKEN", raising=False)
    control_plane, repository, _ = _make_control_plane(tmp_path)

    patched = patch_system_settings(
        control_plane,
        {
            "asr_provider": "capswriter",
            "asr_endpoint": "ws://capswriter.local:6016",
            "asr_language": "auto",
            "asr_context": "课程背景",
            "asr_timeout_seconds": 1200,
        },
    )

    assert patched["asr_provider"] == "capswriter"
    assert patched["asr_token_configured"] is False
    assert repository.get_setting("asr_endpoint") == '"ws://capswriter.local:6016"'


def test_settings_configured_flags_do_not_treat_legacy_env_as_new_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAPSWRITER_TOKEN", "legacy-asr")
    monkeypatch.setenv("QWEN_API_KEY", "legacy-vlm")
    monkeypatch.setenv("SUMMARY_API_KEY", "legacy-summary")
    control_plane, _, _ = _make_control_plane(tmp_path)

    settings = get_system_settings(control_plane)

    assert settings["asr_token_configured"] is False
    assert settings["vlm_api_key_configured"] is False
    assert settings["summary_api_key_configured"] is False


def test_settings_persists_encrypted_provider_secrets_and_snapshots_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for env_name in ("CAPSWRITER_TOKEN", "QWEN_API_KEY", "SUMMARY_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)
    control_plane, repository, _ = _make_control_plane(tmp_path)

    patched = patch_system_settings(
        control_plane,
        {
            "asr_token": "asr-secret",
            "vlm_api_key": "vlm-secret",
            "summary_api_key": "summary-secret",
        },
    )
    assert patched["asr_token_configured"] is True
    assert patched["vlm_api_key_configured"] is True
    assert patched["summary_api_key_configured"] is True
    assert "asr_token" not in patched
    assert "vlm_api_key" not in patched
    assert "summary_api_key" not in patched

    asr_secret = repository.get_active_provider_secret("capswriter_token")
    vlm_secret = repository.get_active_provider_secret("vlm_api_key")
    summary_secret = repository.get_active_provider_secret("summary_api_key")
    assert asr_secret is not None
    assert vlm_secret is not None
    assert summary_secret is not None
    assert "asr-secret" not in asr_secret.secret_encrypted
    assert "vlm-secret" not in vlm_secret.secret_encrypted
    assert "summary-secret" not in summary_secret.secret_encrypted

    project_id = create_project(control_plane, {"title": "provider refs"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]
    snapshot_path = FileSystemWorkspaceStore(tmp_path / "workspaces").config_snapshot_file(
        project_id, job_id
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["asr"]["credential_ref"] == asr_secret.id
    assert snapshot["frame_summary"]["credential_ref"] == vlm_secret.id
    assert snapshot["overall_summary"]["credential_ref"] == summary_secret.id
    assert "asr-secret" not in snapshot_path.read_text(encoding="utf-8")
    assert "vlm-secret" not in snapshot_path.read_text(encoding="utf-8")
    assert "summary-secret" not in snapshot_path.read_text(encoding="utf-8")

    _ = patch_system_settings(
        control_plane,
        {"vlm_api_key": "replacement-vlm-secret"},
    )
    replacement = repository.get_active_provider_secret("vlm_api_key")
    assert replacement is not None
    assert replacement.id != vlm_secret.id
    assert repository.get_provider_secret(vlm_secret.id, expected_kind="vlm_api_key") is not None

    cleared = patch_system_settings(control_plane, {"clear_vlm_api_key": True})
    assert cleared["vlm_api_key_configured"] is False


def test_settings_rejects_replacing_and_clearing_same_secret(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    with pytest.raises(ApiError) as exc_info:
        patch_system_settings(
            control_plane,
            {"vlm_api_key": "new-secret", "clear_vlm_api_key": True},
        )

    assert exc_info.value.code == "provider_secret_patch_conflict"


def test_settings_rejects_capswriter_without_endpoint(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    with pytest.raises(Exception) as exc_info:
        patch_system_settings(
            control_plane,
            {"asr_provider": "capswriter", "asr_endpoint": ""},
        )

    assert getattr(exc_info.value, "code", None) == "asr_endpoint_required"


def test_local_jobs_have_no_guest_cooldown(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]

    first = create_job(control_plane, {"project_id": project_id})
    second = create_job(control_plane, {"project_id": project_id})
    assert first["job_id"] != second["job_id"]
    logs = repository.list_recent_operation_logs(limit=10)
    assert all(log.actor_type == "local" for log in logs)
    assert all(log.actor_id == "local" for log in logs)
    assert sum(log.action == "job.submit" for log in logs) == 2
