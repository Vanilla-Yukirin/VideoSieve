from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import apps.api.service as api_service
import pytest
from apps.api.rest import (
    REST_ROUTES,
    control_job,
    create_job,
    create_me_cookie,
    create_project,
    delete_project,
    get_auth_bootstrap_status,
    get_project,
    get_guest_cooldown,
    get_job_snapshot,
    get_public_access_flags,
    get_system_settings,
    list_project_jobs,
    list_job_artifacts,
    patch_system_settings,
    post_auth_bootstrap,
    post_auth_login,
    probe_ingest_formats,
)
from apps.api.service import ApiControlPlane, ApiError
from pydantic import ValidationError

from contracts import ControlCommandType, JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, RedisEventBus, SQLiteJobRepository
from ingest import IngestFormatOption, IngestFormatProbeResult


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


def _make_control_plane(
    tmp_path: Path,
    *,
    job_dispatcher: Callable[[str, str], None] | None = None,
) -> tuple[ApiControlPlane, SQLiteJobRepository, RedisEventBus]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = RedisEventBus(stub_mode=True)
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
        job_dispatcher=job_dispatcher,
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


def test_rest_project_job_snapshot_and_artifact_list(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    repository.update_project_status(project_id, JobStatus.RUNNING.value)
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.job_path(project_id, job_id, "outputs", "clean_transcript.md").write_text(
        "ok", encoding="utf-8"
    )

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


def test_delete_project_removes_workspace_and_metadata(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
        job_dispatcher=lambda _project_id, _job_id: None,
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
        job_dispatcher=lambda _project_id, _job_id: None,
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
        job_dispatcher=lambda _project_id, _job_id: None,
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
    bus = RedisEventBus(stub_mode=True)

    def _noop_dispatch(
        _project_id: str, _job_id: str, _command: ControlCommandType
    ) -> dict[str, str | bool]:
        return {"command": "cancel", "accepted": True}

    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
        control_dispatcher=_noop_dispatch,
        job_dispatcher=lambda _project_id, _job_id: None,
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
        job_dispatcher=lambda _project_id, _job_id: None,
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
        job_dispatcher=lambda _project_id, _job_id: None,
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
    control_plane._dispatch_job_if_needed = lambda _project_id, _job_id: None  # type: ignore[method-assign]

    from apps.api.models import JobCreateRequest

    project_lock = control_plane._get_project_lock(project_id)  # type: ignore[attr-defined]
    project_lock.acquire()
    worker_started = threading.Event()

    def _runner() -> None:
        worker_started.set()
        try:
            control_plane.create_job(JobCreateRequest(project_id=project_id), actor="user")
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
        job_dispatcher=lambda _project_id, _job_id: None,
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
    def _failing_dispatcher(_project_id: str, _job_id: str) -> None:
        raise RuntimeError("boom")

    control_plane, repository, bus = _make_control_plane(
        tmp_path,
        job_dispatcher=_failing_dispatcher,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    restarted = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
        job_dispatcher=lambda _project_id, _job_id: None,
    )
    snapshot = get_job_snapshot(restarted, job_id)
    assert any("任务派发失败" in line for line in snapshot["latest_logs"])


def test_job_snapshot_merges_persisted_and_memory_logs_without_overlap_duplicates(
    tmp_path: Path,
) -> None:
    control_plane, _, bus = _make_control_plane(
        tmp_path,
        job_dispatcher=lambda _project_id, _job_id: None,
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


def test_mark_dispatch_failure_ignores_worker_log_write_errors(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
        job_dispatcher=lambda _project_id, _job_id: None,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    blocked_parent = tmp_path / "blocked-api"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    control_plane._workspace.worker_log_file = (  # type: ignore[method-assign]
        lambda _project_id, _job_id: blocked_parent / "worker.log"
    )

    control_plane._mark_dispatch_failure(project_id, job_id, RuntimeError("boom"))

    job = repository.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "PIPELINE_DISPATCH_FAILED"


def test_non_default_job_dispatcher_failure_marks_job_failed(tmp_path: Path) -> None:
    def _failing_dispatcher(_project_id: str, _job_id: str) -> None:
        raise RuntimeError("boom")

    control_plane, repository, _ = _make_control_plane(
        tmp_path,
        job_dispatcher=_failing_dispatcher,
    )
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    job = repository.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "PIPELINE_DISPATCH_FAILED"
    assert "boom" in (job.error_message or "")


def test_rest_control_commands_are_job_scoped(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(
        tmp_path,
        job_dispatcher=lambda _project_id, _job_id: None,
    )

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    for command in ("pause", "resume", "cancel", "delete"):
        ack = control_job(control_plane, job_id=job_id, command=command)
        assert ack["command"] == command
        assert "accepted" in ack

    job = repository.get_job(job_id)
    assert job is not None
    assert job.status in {
        JobStatus.QUEUED.value,
        JobStatus.PAUSED.value,
        JobStatus.RUNNING.value,
        JobStatus.CANCEL_REQUESTED.value,
        JobStatus.CANCELLED.value,
    }


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
    cookie = create_me_cookie(
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
    cookie = create_me_cookie(
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


def test_create_job_dispatch_advances_status_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pipeline.orchestrator as orchestrator_module
    from contracts import SourceType
    from ingest import IngestMeta, IngestRequest, IngestResult

    control_plane, repository, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]

    def _fake_run_ingest(
        workspace: FileSystemWorkspaceStore,
        request: IngestRequest,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> IngestResult:
        _ = cancel_checker
        workspace.ensure_job_layout(request.project_id, request.job_id)
        source_path = workspace.source_video_file(request.project_id, request.job_id)
        source_path.write_bytes(b"video")
        meta = IngestMeta(
            project_id=request.project_id,
            job_id=request.job_id,
            source_type=SourceType.BILIBILI_URL,
            source_ref=request.source_url or "https://example.invalid/video",
            title=request.title or "demo",
            description=request.description,
            tags=request.tags,
            language_hint=request.language_hint,
            ingested_at=datetime.now(UTC),
        )
        workspace.job_meta_file(request.project_id, request.job_id).write_text(
            meta.model_dump_json(indent=2), encoding="utf-8"
        )
        return IngestResult(
            project_id=request.project_id,
            job_id=request.job_id,
            source_video_path=str(source_path),
            meta_path=str(workspace.job_meta_file(request.project_id, request.job_id)),
            meta=meta,
        )

    monkeypatch.setattr(orchestrator_module, "run_ingest", _fake_run_ingest)

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

    progressed = _wait_until(
        lambda: (
            (repository.get_job(job_id) is not None)
            and (repository.get_job(job_id).status != JobStatus.QUEUED.value)
        )
    )
    assert progressed

    settled = _wait_until(
        lambda: (
            lambda snap: (
                (snap["current_stage"] is not None)
                or (snap["status"] in {JobStatus.FAILED.value, JobStatus.CANCELLED.value})
            )
        )(get_job_snapshot(control_plane, job_id))
    )
    assert settled

    snapshot = get_job_snapshot(control_plane, job_id)
    progress_value = snapshot["progress"]
    assert isinstance(progress_value, (int, float))
    progress = float(progress_value)
    assert snapshot["status"] in {
        JobStatus.RUNNING.value,
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }
    if snapshot["status"] in {JobStatus.RUNNING.value, JobStatus.SUCCEEDED.value}:
        assert snapshot["current_stage"] is not None
    assert progress >= 0.0


def test_create_job_dispatch_has_duplicate_guard(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def _dispatcher(project_id: str, job_id: str) -> None:
        calls.append((project_id, job_id))

    control_plane, _, _ = _make_control_plane(tmp_path, job_dispatcher=_dispatcher)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    control_plane._dispatch_job_if_needed(project_id, job_id)
    assert calls == [(project_id, job_id)]


def test_auth_bootstrap_login_and_settings_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GUEST_COOKIE_KEY", "guest-key")
    control_plane, repository, _ = _make_control_plane(tmp_path)

    status = get_auth_bootstrap_status(control_plane)
    assert status["bootstrap_required"] is True
    assert "GET /auth/bootstrap-status" in REST_ROUTES

    boot = post_auth_bootstrap(control_plane, {"username": "admin", "password": "password123"})
    token = boot["token"]
    assert boot["username"] == "admin"
    auth_user = repository.get_auth_user()
    assert auth_user is not None
    assert auth_user.username == "admin"

    me_settings = get_system_settings(control_plane, token)
    assert "guest_mode_enabled" in me_settings
    assert "guest_allow_cookie_input" in me_settings

    patched = patch_system_settings(
        control_plane,
        token,
        {"guest_mode_enabled": True, "guest_allow_cookie_input": True},
    )
    assert patched["guest_allow_cookie_input"] is True
    assert repository.get_setting("guest_mode_enabled") == "true"
    assert repository.get_setting("guest_allow_cookie_input") == "true"

    login = post_auth_login(control_plane, {"username": "admin", "password": "password123"})
    assert login["username"] == "admin"
    assert repository.list_recent_operation_logs(limit=5)


def test_guest_cooldown_rejects_second_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GUEST_JOB_COOLDOWN_SECONDS", "360")
    control_plane, repository, _ = _make_control_plane(tmp_path)
    project_id = create_project(control_plane, {"title": "demo"})["project_id"]

    _ = create_job(control_plane, {"project_id": project_id}, actor="guest")
    cooldown = get_guest_cooldown(control_plane)
    assert cooldown["active"] is True
    assert int(str(cooldown["remaining_seconds"])) >= 1
    assert repository.get_next_allowed_at() is not None

    with pytest.raises(Exception) as exc_info:
        create_job(control_plane, {"project_id": project_id}, actor="guest")
    assert getattr(exc_info.value, "code", None) == "guest_cooldown_active"
    logs = repository.list_recent_operation_logs(limit=10)
    assert any(log.action == "guest.job_submit" for log in logs)


def test_settings_rejects_guest_cookie_input_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUEST_COOKIE_KEY", raising=False)
    control_plane, repository, _ = _make_control_plane(tmp_path)
    token = post_auth_bootstrap(control_plane, {"username": "admin", "password": "password123"})[
        "token"
    ]

    with pytest.raises(Exception) as exc_info:
        patch_system_settings(control_plane, token, {"guest_allow_cookie_input": True})
    assert getattr(exc_info.value, "code", None) == "guest_cookie_key_required"
    logs = repository.list_recent_operation_logs(limit=5)
    assert any(log.reason_code == "guest_cookie_key_required" for log in logs)


def test_public_access_flags_is_unauthenticated_and_minimal(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    flags = get_public_access_flags(control_plane)
    assert "GET /public/access-flags" in REST_ROUTES
    assert set(flags.keys()) == {"guest_mode_enabled"}
    assert isinstance(flags["guest_mode_enabled"], bool)


def test_public_access_flags_matches_settings_value(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)
    token = post_auth_bootstrap(control_plane, {"username": "admin", "password": "password123"})[
        "token"
    ]
    _ = patch_system_settings(control_plane, token, {"guest_mode_enabled": False})

    flags = get_public_access_flags(control_plane)
    settings = get_system_settings(control_plane, token)
    assert flags["guest_mode_enabled"] is False
    assert flags["guest_mode_enabled"] == settings["guest_mode_enabled"]


def test_public_access_flags_handles_invalid_db_setting_value(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)
    repository.set_setting("guest_mode_enabled", '"not-a-bool"')

    flags = get_public_access_flags(control_plane)
    assert isinstance(flags["guest_mode_enabled"], bool)
