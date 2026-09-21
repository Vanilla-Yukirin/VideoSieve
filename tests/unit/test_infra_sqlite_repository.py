from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from infra import InfraEvent, SQLiteJobRepository


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


def test_sqlite_repository_persists_job_delete_pending_flag(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-5", title="Demo", status="queued")
    repo.create_job("j-30", "p-5", status="queued", stage="ingest")

    before = repo.get_job("j-30")
    assert before is not None
    assert before.delete_pending is False

    repo.set_job_delete_pending("j-30", True)
    marked = repo.get_job("j-30")
    assert marked is not None
    assert marked.delete_pending is True
    assert repo.list_pending_delete_job_ids() == ["j-30"]

    repo.set_job_delete_pending("j-30", False)
    cleared = repo.get_job("j-30")
    assert cleared is not None
    assert cleared.delete_pending is False
    assert repo.list_pending_delete_job_ids() == []
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

    assert repo.get_setting("asr_provider") is None
    repo.set_setting("asr_provider", '"capswriter"')
    assert repo.get_setting("asr_provider") == '"capswriter"'

    repo.set_setting("asr_provider", '"unconfigured"')
    assert repo.get_setting("asr_provider") == '"unconfigured"'
    repo.close()


def test_sqlite_repository_versions_provider_secrets(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    repo.create_provider_secret(
        secret_id="s-old",
        kind="vlm_api_key",
        secret_encrypted="encrypted-old",
    )
    first = repo.get_active_provider_secret("vlm_api_key")
    assert first is not None
    assert first.id == "s-old"

    repo.create_provider_secret(
        secret_id="s-new",
        kind="vlm_api_key",
        secret_encrypted="encrypted-new",
    )
    active = repo.get_active_provider_secret("vlm_api_key")
    old = repo.get_provider_secret("s-old", expected_kind="vlm_api_key")
    assert active is not None
    assert active.id == "s-new"
    assert old is not None
    assert old.superseded_at is not None
    assert repo.get_provider_secret("s-new", expected_kind="summary_api_key") is None

    repo.clear_active_provider_secret("vlm_api_key")
    assert repo.get_active_provider_secret("vlm_api_key") is None
    assert repo.get_provider_secret("s-new", expected_kind="vlm_api_key") is not None
    repo.close()


def test_sqlite_repository_drops_legacy_auth_tables_without_losing_vault_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "infra.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE auth_user (
          id TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO auth_user VALUES ('u-1', 'admin', 'hash', 'now', 'now');
        CREATE TABLE guest_cooldown (
          key TEXT PRIMARY KEY,
          next_allowed_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO guest_cooldown VALUES ('global', 'later', 'now');
        CREATE TABLE user_cookies (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          name TEXT NOT NULL,
          cookie_encrypted TEXT NOT NULL,
          is_default INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          last_validated_at TEXT,
          last_error_code TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO user_cookies VALUES (
          'c-legacy', 'default_user', 'legacy', 'encrypted-cookie', 1,
          'unknown', NULL, NULL, 'now', 'now'
        );
        CREATE TABLE provider_secrets (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          secret_encrypted TEXT NOT NULL,
          created_at TEXT NOT NULL,
          superseded_at TEXT
        );
        INSERT INTO provider_secrets VALUES (
          's-legacy', 'vlm_api_key', 'encrypted-secret', 'now', NULL
        );
        CREATE TABLE system_settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO system_settings VALUES ('guest_mode_enabled', 'true', 'now');
        INSERT INTO system_settings VALUES ('guest_allow_cookie_input', 'true', 'now');
        INSERT INTO system_settings VALUES ('asr_provider', '"capswriter"', 'now');
        """
    )
    conn.commit()
    conn.close()

    repo = SQLiteJobRepository(db_path)
    repo.ensure_schema()

    inspection = sqlite3.connect(db_path)
    table_names = {
        str(row[0])
        for row in inspection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    inspection.close()
    assert "auth_user" not in table_names
    assert "guest_cooldown" not in table_names
    cookie = repo.get_user_cookie("c-legacy", "default_user")
    secret = repo.get_provider_secret("s-legacy", expected_kind="vlm_api_key")
    assert cookie is not None
    assert cookie.cookie_encrypted == "encrypted-cookie"
    assert secret is not None
    assert secret.secret_encrypted == "encrypted-secret"
    assert repo.get_setting("guest_mode_enabled") is None
    assert repo.get_setting("guest_allow_cookie_input") is None
    assert repo.get_setting("asr_provider") == '"capswriter"'
    repo.close()


def test_sqlite_repository_operation_logs_append_and_list_recent(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()

    repo.append_operation_log(
        log_id="l-1",
        actor_type="local",
        actor_id="local",
        action="job.submit",
        status="accepted",
        reason_code=None,
        created_at="2026-01-01T00:00:00+00:00",
        meta_json='{"job_id":"j-1"}',
    )
    repo.append_operation_log(
        log_id="l-2",
        actor_type="local",
        actor_id="local",
        action="settings.patch",
        status="success",
        reason_code=None,
        created_at="2026-01-01T00:00:01+00:00",
        meta_json='{"ip":"127.0.0.1"}',
    )

    rows = repo.list_recent_operation_logs(limit=10)
    assert [row.id for row in rows] == ["l-2", "l-1"]
    assert rows[0].status == "success"
    assert rows[1].action == "job.submit"
    repo.close()


def test_worker_attempt_fences_progress_and_terminal_state(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-fence", title="demo", status="queued")
    repo.create_job("j-fence", "p-fence", status="queued", stage=None)

    first = repo.claim_next_job("worker-old")
    assert first is not None
    assert repo.update_job_progress(
        "j-fence",
        progress=25.0,
        stage="asr",
        expected_worker_id="worker-old",
        expected_attempt=first.attempt,
    )
    stale_before = datetime.now(UTC) + timedelta(microseconds=1)
    assert repo.mark_stale_jobs_interrupted(stale_before) == ["j-fence"]
    assert repo.recover_interrupted_job("j-fence")
    second = repo.claim_next_job("worker-new")
    assert second is not None

    assert not repo.update_job_status(
        "j-fence",
        status="succeeded",
        stage="deliverables",
        expected_worker_id="worker-old",
        expected_attempt=first.attempt,
    )
    assert repo.update_job_progress(
        "j-fence",
        progress=50.0,
        stage="keyframes",
        expected_worker_id="worker-new",
        expected_attempt=second.attempt,
    )
    current = repo.get_job("j-fence")
    assert current is not None
    assert current.status == "running"
    assert current.progress == 50.0
    assert current.attempt == 2
    repo.close()


def test_control_request_is_conditional_idempotent_and_cancels_unowned_job(
    tmp_path: Path,
) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-control", title="demo", status="queued")
    repo.create_job("j-control", "p-control", status="queued", stage=None)
    before = repo.get_job("j-control")
    assert before is not None

    version = repo.request_job_control(
        "j-control",
        "cancel",
        request_id="request-1",
        expected_status=before.status,
        expected_state_version=before.state_version,
        finalize_cancel_if_unowned=True,
    )
    assert version == 1
    replayed = repo.request_job_control(
        "j-control",
        "cancel",
        request_id="request-1",
        expected_status=before.status,
        expected_state_version=before.state_version,
        finalize_cancel_if_unowned=True,
    )
    assert replayed == version
    cancelled = repo.get_job("j-control")
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.control_ack_version == version
    assert repo.claim_next_job("worker-too-late") is None
    assert (
        repo.request_job_control(
            "j-control",
            "pause",
            request_id="request-2",
            expected_status="queued",
            expected_state_version=before.state_version,
        )
        is None
    )
    repo.close()


def test_delete_job_and_project_remove_persisted_events(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-events", title="demo", status="queued")
    repo.create_job("j-one", "p-events", status="queued", stage=None)
    repo.create_job("j-two", "p-events", status="queued", stage=None)
    for job_id in ("j-one", "j-two"):
        repo.append_job_event(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="log",
                project_id="p-events",
                job_id=job_id,
                payload={"message": job_id},
            ),
        )

    repo.delete_job("j-one")
    assert repo.list_job_events("jobs:j-one") == []
    repo.delete_project("p-events")
    assert repo.list_job_events("jobs:j-two") == []
    repo.close()


def test_project_status_is_derived_across_multiple_jobs(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(tmp_path / "infra.db")
    repo.ensure_schema()
    repo.upsert_project("p-many", title="demo", status="queued")
    repo.create_job("j-done", "p-many", status="succeeded", stage="deliverables")
    repo.create_job("j-active", "p-many", status="running", stage="asr")

    assert repo.refresh_project_status("p-many") == "running"
    repo.update_job_status("j-active", status="failed", stage="asr")
    assert repo.refresh_project_status("p-many") == "failed"
    project = repo.get_project("p-many")
    assert project is not None
    assert project.status == "failed"
    repo.close()
