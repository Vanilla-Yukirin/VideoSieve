from __future__ import annotations

from pathlib import Path

import pytest
from apps.api.models import ProjectCreateRequest
from apps.api.rest import REST_ROUTES, list_projects
from apps.api.service import ApiControlPlane

import infra.sqlite_repository as sqlite_repository_module
from infra import FileSystemWorkspaceStore, InMemoryEventBus, SQLiteJobRepository


def test_sqlite_project_list_is_newest_first_with_stable_tiebreaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamps = iter(
        [
            "2025-12-31T00:00:00+00:00",  # schema legacy-state reconciliation
            "2026-01-01T00:00:00+00:00",
            "2026-01-02T00:00:00+00:00",
            "2026-01-02T00:00:00+00:00",
        ]
    )
    monkeypatch.setattr(sqlite_repository_module, "_utc_now_iso", lambda: next(timestamps))
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.upsert_project("p-old", title="Old", status="queued")
    repository.upsert_project("p-a", title="A", status="queued")
    repository.upsert_project("p-b", title=None, status="running")

    projects = repository.list_projects()

    assert [project.project_id for project in projects] == ["p-b", "p-a", "p-old"]
    assert projects[0].title is None
    assert projects[0].status == "running"
    repository.close()


def test_rest_project_list_serializes_sqlite_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=InMemoryEventBus(),
    )
    project_id = control_plane.create_project(ProjectCreateRequest(title="Persisted"))

    projects = list_projects(control_plane)

    assert "GET /projects" in REST_ROUTES
    assert projects == [
        {
            "project_id": project_id,
            "title": "Persisted",
            "status": "queued",
            "created_at": repository.get_project(project_id).created_at,  # type: ignore[union-attr]
            "updated_at": repository.get_project(project_id).updated_at,  # type: ignore[union-attr]
        }
    ]
    repository.close()
