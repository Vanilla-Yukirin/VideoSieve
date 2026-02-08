from __future__ import annotations

import json
from pathlib import Path

import apps.api.service as api_service
import pytest
from apps.api.rest import (
    REST_ROUTES,
    control_job,
    create_job,
    create_project,
    get_job_snapshot,
    list_job_artifacts,
    probe_ingest_formats,
)
from apps.api.service import ApiControlPlane

from contracts import JobStatus
from infra import FileSystemWorkspaceStore, InfraEvent, RedisEventBus, SQLiteJobRepository
from ingest import IngestFormatOption, IngestFormatProbeResult


def _make_control_plane(
    tmp_path: Path,
) -> tuple[ApiControlPlane, SQLiteJobRepository, RedisEventBus]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = RedisEventBus(stub_mode=True)
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=bus,
    )
    return control_plane, repository, bus


def test_rest_project_job_snapshot_and_artifact_list(tmp_path: Path) -> None:
    control_plane, repository, bus = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(control_plane, {"project_id": project_id})["job_id"]

    repository.update_project_status(project_id, JobStatus.RUNNING.value)
    repository.update_job_status(job_id, status=JobStatus.RUNNING.value, stage="asr")
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.path(project_id, "outputs", "clean_transcript.md").write_text("ok", encoding="utf-8")

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

    snapshot = get_job_snapshot(control_plane, job_id)
    artifacts = list_job_artifacts(control_plane, job_id)

    assert "GET /jobs/{job_id}/snapshot" in REST_ROUTES
    assert snapshot["status"] == JobStatus.RUNNING.value
    assert snapshot["current_stage"] == "asr"
    assert snapshot["progress"] == 27.5
    assert snapshot["latest_logs"] == ["[info] started"]
    assert any(item["path"] == "outputs/clean_transcript.md" for item in artifacts)


def test_rest_control_commands_are_job_scoped(tmp_path: Path) -> None:
    control_plane, repository, _ = _make_control_plane(tmp_path)

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
    assert "resolution" in formats[0]
    assert "fps" in formats[0]
    assert "tbr" in formats[0]
    assert "vcodec" in formats[0]
    assert "acodec" in formats[0]
    assert "is_video_only" in formats[0]
    assert "is_audio_only" in formats[0]


def test_create_job_persists_ingest_format_selection_in_snapshot(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    job_id = create_job(
        control_plane,
        {
            "project_id": project_id,
            "ingest": {
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "video_format_id": "30116",
                "audio_format_id": "30280",
                "cookie_secret_ref": "secrets/bili/prod",
            },
        },
    )["job_id"]

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    snapshot_path = workspace.path(project_id, "meta", "config.snapshot.json")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ingest = payload["ingest"]

    assert payload["job_id"] == job_id
    assert ingest["source_url"] == "https://www.bilibili.com/video/BV1demo"
    assert ingest["video_format_id"] == "30116"
    assert ingest["audio_format_id"] == "30280"
    assert ingest["cookie_secret_ref"] == "secrets/bili/prod"


def test_create_job_backward_compatible_without_format_selection(tmp_path: Path) -> None:
    control_plane, _, _ = _make_control_plane(tmp_path)

    project_id = create_project(control_plane, {"title": "demo"})["project_id"]
    create_job(
        control_plane,
        {
            "project_id": project_id,
            "ingest": {
                "source_url": "https://www.bilibili.com/video/BV1compat",
            },
        },
    )

    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    snapshot_path = workspace.path(project_id, "meta", "config.snapshot.json")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ingest = payload["ingest"]

    assert ingest["source_url"] == "https://www.bilibili.com/video/BV1compat"
    assert "video_format_id" not in ingest
    assert "audio_format_id" not in ingest
