from __future__ import annotations

import json
from pathlib import Path

import pytest
from apps.api.models import (
    IngestAssetSelection,
    IngestParams,
    JobCreateRequest,
    ProjectCreateRequest,
)
from apps.api.rest import create_job as rest_create_job
from apps.api.service import ApiControlPlane
from pydantic import ValidationError

from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


def _make_control_plane(tmp_path: Path) -> tuple[ApiControlPlane, FileSystemWorkspaceStore]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    bus = RedisEventBus(stub_mode=True)
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=workspace,
        event_bus=bus,
    )
    return control_plane, workspace


def test_create_job_with_ingest_params(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="ingest_test"))
    ingest = IngestParams(
        source_url="https://test.com/video", video_format_id="1080p", audio_format_id="hq"
    )
    job_req = JobCreateRequest(project_id=pid, ingest=ingest, summary_enabled=True)
    jid = control_plane.create_job(job_req)

    config_path = workspace.path(pid, "meta", "config.snapshot.json")
    assert config_path.exists()

    data = json.loads(config_path.read_text("utf-8"))
    assert data["project_id"] == pid
    assert data["job_id"] == jid
    assert data["summary_enabled"] is True
    assert data["dedupe_applied_estimate"] is True
    assert "ingest" in data
    assert data["ingest"]["source_url"] == "https://test.com/video"
    assert data["ingest"]["analysis_asset"] == {"video_format_id": "1080p", "audio_format_id": "hq"}
    assert data["ingest"]["quality_asset"] == {"video_format_id": "1080p", "audio_format_id": "hq"}


def test_create_job_backward_compatibility_without_ingest(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="legacy_test"))

    job_req = JobCreateRequest(project_id=pid)
    jid = control_plane.create_job(job_req)

    config_path = workspace.path(pid, "meta", "config.snapshot.json")
    data = json.loads(config_path.read_text("utf-8"))

    assert "ingest" not in data
    assert data["job_id"] == jid


def test_create_job_normalizes_analysis_only_payload(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="analysis_only"))

    jid = control_plane.create_job(
        JobCreateRequest(
            project_id=pid,
            ingest=IngestParams(
                source_url="https://test.com/video",
                analysis_asset=IngestAssetSelection(
                    video_format_id="30032", audio_format_id="30280"
                ),
            ),
        )
    )

    data = json.loads(workspace.path(pid, "meta", "config.snapshot.json").read_text("utf-8"))
    assert data["job_id"] == jid
    assert data["ingest"]["analysis_asset"] == {
        "video_format_id": "30032",
        "audio_format_id": "30280",
    }
    assert data["ingest"]["quality_asset"] == {
        "video_format_id": "30032",
        "audio_format_id": "30280",
    }
    assert data["dedupe_applied_estimate"] is True


def test_create_job_normalizes_quality_only_payload(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="quality_only"))

    control_plane.create_job(
        JobCreateRequest(
            project_id=pid,
            ingest=IngestParams(
                source_url="https://test.com/video",
                quality_asset=IngestAssetSelection(
                    video_format_id="30116", audio_format_id="30280"
                ),
            ),
        )
    )

    data = json.loads(workspace.path(pid, "meta", "config.snapshot.json").read_text("utf-8"))
    assert data["ingest"]["analysis_asset"] == {
        "video_format_id": "30116",
        "audio_format_id": "30280",
    }
    assert data["ingest"]["quality_asset"] == {
        "video_format_id": "30116",
        "audio_format_id": "30280",
    }
    assert data["dedupe_applied_estimate"] is True


def test_create_job_allows_no_format_selection_with_default_strategy(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="default_strategy"))

    control_plane.create_job(
        JobCreateRequest(
            project_id=pid,
            ingest=IngestParams(source_url="https://test.com/video"),
        )
    )

    data = json.loads(workspace.path(pid, "meta", "config.snapshot.json").read_text("utf-8"))
    assert data["ingest"]["source_url"] == "https://test.com/video"
    assert "analysis_asset" not in data["ingest"]
    assert "quality_asset" not in data["ingest"]
    assert data["dedupe_applied_estimate"] is True


def test_create_job_rejects_ytdlp_advanced_fields(tmp_path: Path) -> None:
    control_plane, _ = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="reject_advanced"))

    with pytest.raises(ValidationError):
        rest_create_job(
            control_plane,
            {
                "project_id": pid,
                "ingest": {
                    "source_url": "https://test.com/video",
                    "ytdlp_sort": "res,br",
                },
            },
        )


def test_create_job_persists_cookie_id_when_present(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="cookie_id"))
    control_plane._repository.set_setting("guest_allow_cookie_input", "true")

    control_plane.create_job(
        JobCreateRequest(
            project_id=pid,
            ingest=IngestParams(
                source_url="https://test.com/video",
                cookie_id="c_demo123",
            ),
        )
    )

    data = json.loads(workspace.path(pid, "meta", "config.snapshot.json").read_text("utf-8"))
    assert data["ingest"]["cookie_id"] == "c_demo123"
    assert "cookie_file_path" not in data["ingest"]


def test_create_job_cookie_id_takes_priority_over_cookie_file_path(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="cookie_priority"))
    control_plane._repository.set_setting("guest_allow_cookie_input", "true")

    control_plane.create_job(
        JobCreateRequest(
            project_id=pid,
            ingest=IngestParams(
                source_url="https://test.com/video",
                cookie_id="c_priority",
                cookie_file_path="/tmp/legacy.cookies.txt",
            ),
        )
    )

    data = json.loads(workspace.path(pid, "meta", "config.snapshot.json").read_text("utf-8"))
    assert data["ingest"]["cookie_id"] == "c_priority"
    assert "cookie_file_path" not in data["ingest"]


def test_create_job_rejects_cookie_content_in_payload(tmp_path: Path) -> None:
    control_plane, _ = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="reject_cookie_content"))

    with pytest.raises(ValidationError):
        rest_create_job(
            control_plane,
            {
                "project_id": pid,
                "ingest": {
                    "source_url": "https://test.com/video",
                    "cookie_content": "SESSDATA=plaintext",
                },
            },
        )

    with pytest.raises(ValidationError):
        rest_create_job(
            control_plane,
            {
                "project_id": pid,
                "ingest": {
                    "source_url": "https://test.com/video",
                    "ytdlp_format": "bestvideo+bestaudio",
                },
            },
        )
