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


def test_sqlite_repository_user_cookie_crud_and_default_switch(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    repo.create_user_cookie(
        cookie_id="c-1",
        user_id="u-1",
        name="main",
        cookie_encrypted="enc-1",
        is_default=True,
        status="unknown",
    )
    repo.create_user_cookie(
        cookie_id="c-2",
        user_id="u-1",
        name="backup",
        cookie_encrypted="enc-2",
        is_default=False,
        status="unknown",
    )

    rows = repo.list_user_cookies("u-1")
    assert [row.id for row in rows] == ["c-1", "c-2"]
    assert rows[0].is_default is True

    repo.clear_default_cookie_for_user("u-1")
    repo.update_user_cookie(cookie_id="c-2", user_id="u-1", is_default=True)

    updated_first = repo.get_user_cookie("c-1", "u-1")
    updated_second = repo.get_user_cookie("c-2", "u-1")
    assert updated_first is not None
    assert updated_second is not None
    assert updated_first.is_default is False
    assert updated_second.is_default is True

    repo.update_user_cookie(
        cookie_id="c-2",
        user_id="u-1",
        status="valid",
        last_validated_at="2026-01-01T00:00:00+00:00",
        last_error_code=None,
        set_last_validated_at=True,
        set_last_error_code=True,
    )
    validated = repo.get_user_cookie("c-2", "u-1")
    assert validated is not None
    assert validated.status == "valid"
    assert validated.last_validated_at == "2026-01-01T00:00:00+00:00"
    assert validated.last_error_code is None

    repo.delete_user_cookie("c-1", "u-1")
    assert repo.get_user_cookie("c-1", "u-1") is None
    repo.close()
