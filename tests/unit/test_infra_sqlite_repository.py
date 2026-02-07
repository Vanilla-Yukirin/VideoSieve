from __future__ import annotations

from pathlib import Path

from infra import SQLiteJobRepository


def test_sqlite_repository_project_and_job_crud(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    repo.upsert_project("p-1", title="Demo", status="queued")
    repo.create_job("j-1", "p-1", status="queued", stage="ingest")

    project = repo.get_project("p-1")
    assert project is not None
    assert project.project_id == "p-1"
    assert project.title == "Demo"
    assert project.status == "queued"

    job = repo.get_job("j-1")
    assert job is not None
    assert job.project_id == "p-1"
    assert job.status == "queued"
    assert job.stage == "ingest"

    repo.update_project_status("p-1", "running")
    repo.update_job_status("j-1", status="running", stage="asr")

    updated_project = repo.get_project("p-1")
    updated_job = repo.get_job("j-1")
    assert updated_project is not None
    assert updated_job is not None
    assert updated_project.status == "running"
    assert updated_job.status == "running"
    assert updated_job.stage == "asr"

    repo.close()


def test_sqlite_repository_list_jobs_ordered(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-2", title=None, status="queued")

    repo.create_job("j-1", "p-2", status="queued", stage="ingest")
    repo.create_job("j-2", "p-2", status="queued", stage="ingest")

    jobs = repo.list_jobs_for_project("p-2")
    assert [item.job_id for item in jobs] == ["j-1", "j-2"]

    repo.close()
