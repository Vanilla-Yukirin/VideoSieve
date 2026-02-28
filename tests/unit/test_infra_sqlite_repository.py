from __future__ import annotations

from datetime import UTC, datetime
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


def test_sqlite_repository_delete_project_removes_jobs(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-3", title="Demo", status="queued")
    repo.create_job("j-10", "p-3", status="queued", stage="ingest")
    repo.create_job("j-11", "p-3", status="running", stage="asr")

    repo.delete_project("p-3")

    assert repo.get_project("p-3") is None
    assert repo.get_job("j-10") is None
    assert repo.get_job("j-11") is None
    assert repo.list_jobs_for_project("p-3") == []
    repo.close()


def test_sqlite_repository_delete_single_job(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-4", title="Demo", status="queued")
    repo.create_job("j-20", "p-4", status="queued", stage="ingest")

    repo.delete_job("j-20")

    assert repo.get_job("j-20") is None
    assert repo.get_project("p-4") is not None
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


def test_sqlite_repository_settings_upsert_and_get(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    assert repo.get_setting("enable_guest_mode") is None
    repo.set_setting("enable_guest_mode", "true")
    assert repo.get_setting("enable_guest_mode") == "true"

    repo.set_setting("enable_guest_mode", "false")
    assert repo.get_setting("enable_guest_mode") == "false"
    repo.close()


def test_sqlite_repository_auth_user_create_and_password_update(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    assert repo.get_auth_user() is None
    repo.create_auth_user(user_id="u-1", username="admin", password_hash="hash-v1")
    created = repo.get_auth_user()
    assert created is not None
    assert created.id == "u-1"
    assert created.username == "admin"
    assert created.password_hash == "hash-v1"

    repo.update_auth_user_password_hash(user_id="u-1", password_hash="hash-v2")
    updated = repo.get_auth_user()
    assert updated is not None
    assert updated.password_hash == "hash-v2"
    repo.close()


def test_sqlite_repository_operation_logs_append_and_list_recent(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    repo.append_operation_log(
        log_id="l-1",
        actor_type="guest",
        actor_id=None,
        action="guest_submit",
        status="rejected",
        reason_code="guest_cooldown_active",
        created_at="2026-01-01T00:00:00+00:00",
        meta_json='{"job_id":"j-1"}',
    )
    repo.append_operation_log(
        log_id="l-2",
        actor_type="user",
        actor_id="u-1",
        action="login",
        status="success",
        reason_code=None,
        created_at="2026-01-01T00:00:01+00:00",
        meta_json='{"ip":"127.0.0.1"}',
    )

    rows = repo.list_recent_operation_logs(limit=10)
    assert [row.id for row in rows] == ["l-2", "l-1"]
    assert rows[0].status == "success"
    assert rows[1].reason_code == "guest_cooldown_active"
    repo.close()


def test_sqlite_repository_guest_cooldown_try_acquire_atomic(tmp_path: Path) -> None:
    db_path = tmp_path / "infra.db"
    repo_a = SQLiteJobRepository(db_path)
    repo_b = SQLiteJobRepository(db_path)
    repo_a.ensure_schema()

    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert repo_a.try_acquire(now, cooldown_seconds=60) is True
    first_next_allowed = repo_a.get_next_allowed_at()
    assert first_next_allowed == "2026-01-01T00:01:00+00:00"

    assert repo_b.try_acquire(now, cooldown_seconds=60) is False
    assert repo_b.get_next_allowed_at() == "2026-01-01T00:01:00+00:00"

    later = datetime(2026, 1, 1, 0, 1, 1, tzinfo=UTC)
    assert repo_b.try_acquire(later, cooldown_seconds=60) is True
    assert repo_b.get_next_allowed_at() == "2026-01-01T00:02:01+00:00"

    repo_a.close()
    repo_b.close()
