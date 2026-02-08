from __future__ import annotations

import json
from pathlib import Path

from apps.api.models import IngestParams, JobCreateRequest, ProjectCreateRequest
from apps.api.service import ApiControlPlane

from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository


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

    # 1. Create Project
    pid = control_plane.create_project(ProjectCreateRequest(title="ingest_test"))

    # 2. Create Job with Ingest Params
    ingest = IngestParams(
        source_url="https://test.com/video", video_format_id="1080p", audio_format_id="hq"
    )
    job_req = JobCreateRequest(project_id=pid, ingest=ingest)
    jid = control_plane.create_job(job_req)

    # 3. Verify Snapshot
    config_path = workspace.path(pid, "meta", "config.snapshot.json")
    assert config_path.exists()

    data = json.loads(config_path.read_text("utf-8"))
    assert data["project_id"] == pid
    assert data["job_id"] == jid
    assert "ingest" in data
    assert data["ingest"]["source_url"] == "https://test.com/video"
    assert data["ingest"]["video_format_id"] == "1080p"


def test_create_job_backward_compatibility(tmp_path: Path) -> None:
    control_plane, workspace = _make_control_plane(tmp_path)
    pid = control_plane.create_project(ProjectCreateRequest(title="legacy_test"))

    # Legacy request without ingest params
    job_req = JobCreateRequest(project_id=pid)
    jid = control_plane.create_job(job_req)

    config_path = workspace.path(pid, "meta", "config.snapshot.json")
    data = json.loads(config_path.read_text("utf-8"))

    assert "ingest" not in data
    assert data["job_id"] == jid
