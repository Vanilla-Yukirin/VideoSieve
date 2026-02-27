from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


def _make_client(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_stub_mode=True)
    return TestClient(app)


def test_runtime_healthz_and_rest_smoke(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        public_flags = client.get("/public/access-flags")
        assert public_flags.status_code == 200
        assert set(public_flags.json().keys()) == {"guest_mode_enabled"}

        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        created_project = client.post("/projects", json={"title": "demo"})
        assert created_project.status_code == 200
        project_id = created_project.json()["project_id"]

        created_job = client.post("/jobs", json={"project_id": project_id})
        assert created_job.status_code == 200
        job_id = created_job.json()["job_id"]

        fetched_job = client.get(f"/jobs/{job_id}")
        assert fetched_job.status_code == 200
        assert fetched_job.json()["project_id"] == project_id


def test_runtime_source_video_route_returns_file_when_present(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        runtime_root = tmp_path / "runtime" / "workspaces" / project_id / "media"
        runtime_root.mkdir(parents=True, exist_ok=True)
        source_file = runtime_root / "source.mp4"
        source_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        response = client.get(f"/jobs/{job_id}/source-video")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "video/mp4"


def test_runtime_source_video_route_returns_not_found_when_missing(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        response = client.get(f"/jobs/{job_id}/source-video")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_runtime_error_mapping_for_not_found_and_validation(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        missing = client.get("/jobs/j_missing")
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"

        invalid = client.post(
            "/ingest/probe", json={"source_url": "https://test", "ytdlp_sort": "res"}
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "validation_error"


def test_runtime_ws_connect_immediately_receives_snapshot(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        project = client.post("/projects", json={"title": "demo"}).json()
        project_id = project["project_id"]
        job = client.post("/jobs", json={"project_id": project_id}).json()
        job_id = job["job_id"]

        with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            first = ws.receive_json()
            assert first["event_type"] == "snapshot"
            assert first["payload"]["job_id"] == job_id


def test_runtime_startup_fails_when_app_secret_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from apps.api.service import ApiConfigError
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_stub_mode=True)
    with pytest.raises(ApiConfigError, match="APP_SECRET_KEY is required"):
        with TestClient(app):
            pass


def test_runtime_probe_returns_not_found_for_unknown_cookie_id(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        response = client.post(
            "/ingest/probe",
            json={
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "cookie_id": "c_missing",
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_runtime_cookie_validate_requires_source_url(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created = client.post(
            "/me/cookies",
            json={
                "name": "demo",
                "cookie_netscape_text": (
                    "# Netscape HTTP Cookie File\n"
                    ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tdemo\n"
                ),
            },
        )
        cookie_id = created.json()["id"]
        response = client.post(f"/me/cookies/{cookie_id}/validate", json={})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


def test_runtime_cookie_validate_rejects_homepage_url(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created = client.post(
            "/me/cookies",
            json={
                "name": "demo",
                "cookie_netscape_text": (
                    "# Netscape HTTP Cookie File\n"
                    ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tdemo\n"
                ),
            },
        )
        cookie_id = created.json()["id"]
        response = client.post(
            f"/me/cookies/{cookie_id}/validate",
            json={"source_url": "https://www.bilibili.com"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


def test_runtime_auth_bootstrap_login_me_logout_flow(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        status = client.get("/auth/bootstrap-status")
        assert status.status_code == 200
        assert status.json()["bootstrap_required"] is True

        boot = client.post(
            "/auth/bootstrap",
            json={"username": "admin", "password": "password123"},
        )
        assert boot.status_code == 200
        token = boot.json()["token"]

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["username"] == "admin"

        logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout.status_code == 200

        me_after = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_after.status_code == 401
        assert me_after.json()["code"] == "auth_required"
    assert not (tmp_path / "runtime" / "api_state.json").exists()


def test_runtime_settings_patch_requires_guest_cookie_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUEST_COOKIE_KEY", raising=False)
    with _make_client(tmp_path) as client:
        boot = client.post(
            "/auth/bootstrap",
            json={"username": "admin", "password": "password123"},
        )
        token = boot.json()["token"]

        patched = client.patch(
            "/settings/system",
            json={"guest_allow_cookie_input": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patched.status_code == 422
        assert patched.json()["code"] == "guest_cookie_key_required"


def test_runtime_guest_cooldown_shared_for_guest_submissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GUEST_JOB_COOLDOWN_SECONDS", "120")
    with _make_client(tmp_path) as client:
        project = client.post("/projects", json={"title": "demo"}).json()
        project_id = project["project_id"]

        first = client.post("/jobs", json={"project_id": project_id})
        assert first.status_code == 200

        cooldown = client.get("/guest/cooldown")
        assert cooldown.status_code == 200
        assert cooldown.json()["active"] is True
        assert cooldown.json()["cooldown_seconds"] == 120

        second = client.post("/jobs", json={"project_id": project_id})
        assert second.status_code == 429
        assert second.json()["code"] == "guest_cooldown_active"
        assert int(second.json()["remaining_seconds"]) >= 1


def test_runtime_public_access_flags_matches_private_settings(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        boot = client.post(
            "/auth/bootstrap",
            json={"username": "admin", "password": "password123"},
        )
        token = boot.json()["token"]

        patched = client.patch(
            "/settings/system",
            json={"guest_mode_enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patched.status_code == 200

        public_flags = client.get("/public/access-flags")
        assert public_flags.status_code == 200
        payload = public_flags.json()
        assert payload == {"guest_mode_enabled": False}
        assert "guest_allow_cookie_input" not in payload


@pytest.mark.parametrize("raw_value,expected", [("true", True), ("false", False)])
def test_runtime_event_bus_stub_mode_is_configurable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: bool,
) -> None:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("VIDEOSIEVE_EVENTBUS_STUB_MODE", raw_value)
    app = create_app(data_dir=tmp_path / "runtime")
    with TestClient(app) as client:
        _ = client.get("/healthz")
        runtime = cast(Any, client.app).state.runtime
        assert runtime.event_bus._stub_mode is expected
