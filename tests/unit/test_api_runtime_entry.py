from __future__ import annotations

import json
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from infra import InMemoryEventBus, SQLiteEventBus, SQLiteJobRepository


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_GUEST_MODE", "true")


def _make_client(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_in_memory=True)
    return TestClient(app)


def _publish_ready_artifact(
    artifact_file: Path,
    *,
    project_id: str,
    job_id: str,
    content: str = "ok",
) -> None:
    artifact_file.write_text(content, encoding="utf-8")
    data = artifact_file.read_bytes()
    (artifact_file.parent / "deliverables.ready.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "ready": True,
                "project_id": project_id,
                "job_id": job_id,
                "artifacts": [
                    {
                        "path": "outputs/clean_transcript.md",
                        "size_bytes": len(data),
                        "sha256": sha256(data).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


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


def test_runtime_upload_is_staged_inside_project_workspace_with_safe_name(
    tmp_path: Path,
) -> None:
    with _make_client(tmp_path) as client:
        project_id = client.post("/projects", json={"title": "demo"}).json()["project_id"]
        response = client.post(
            f"/projects/{project_id}/jobs/upload",
            files={"video": ("../../unsafe name.mp4", b"video-bytes", "video/mp4")},
            data={"context": "demo", "summary_enabled": "false"},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        config_path = (
            tmp_path
            / "runtime"
            / "workspaces"
            / project_id
            / "jobs"
            / job_id
            / "meta"
            / "config.snapshot.json"
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        staged = Path(config["local_video_path"])
        upload_root = (
            tmp_path / "runtime" / "workspaces" / project_id / "uploads"
        ).resolve()
        assert staged.resolve().is_relative_to(upload_root)
        assert staged.name.startswith("upload_")
        assert staged.suffix == ".mp4"
        assert staged.read_bytes() == b"video-bytes"


def test_runtime_source_video_route_returns_file_when_present(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        runtime_root = tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "media"
        runtime_root.mkdir(parents=True, exist_ok=True)
        source_file = runtime_root / "source.mp4"
        source_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        response = client.get(f"/jobs/{job_id}/source-video")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "video/mp4"


def test_runtime_delete_project_route_removes_project(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]

        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        fetched = client.get(f"/projects/{project_id}")
        assert fetched.status_code == 404


def test_runtime_delete_project_route_blocks_without_force_when_active_jobs(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        assert created_job.status_code == 200

        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 409
        assert response.json()["code"] == "project_has_active_jobs"
        assert isinstance(response.json().get("active_job_ids"), list)


def test_runtime_source_video_route_returns_not_found_when_missing(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        response = client.get(f"/jobs/{job_id}/source-video")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_runtime_artifact_download_route_returns_file_when_present(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        artifact_dir = (
            tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "outputs"
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / "clean_transcript.md"
        _publish_ready_artifact(
            artifact_file,
            project_id=project_id,
            job_id=job_id,
        )

        response = client.get(f"/jobs/{job_id}/artifacts/download/outputs/clean_transcript.md")
        assert response.status_code == 200
        assert response.text == "ok"


def test_runtime_artifact_download_route_rejects_unlisted_file(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        hidden_dir = tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "private"
        hidden_dir.mkdir(parents=True, exist_ok=True)
        hidden_file = hidden_dir / "token.txt"
        hidden_file.write_text("secret", encoding="utf-8")

        response = client.get(f"/jobs/{job_id}/artifacts/download/private/token.txt")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_runtime_artifact_download_route_supports_relative_data_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(data_dir=Path("runtime"), event_bus_in_memory=True)) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        artifact_dir = (
            tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "outputs"
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / "clean_transcript.md"
        _publish_ready_artifact(
            artifact_file,
            project_id=project_id,
            job_id=job_id,
        )

        response = client.get(f"/jobs/{job_id}/artifacts/download/outputs/clean_transcript.md")
        assert response.status_code == 200
        assert response.text == "ok"


def test_runtime_keyframes_zip_route_returns_archive(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        frames_dir = tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "frames"
        images_dir = frames_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / "slide_000001.jpg").write_bytes(b"fake-jpg-1")
        (images_dir / "slide_000002.jpeg").write_bytes(b"fake-jpg-2")
        zip_path = frames_dir / "images.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("slide_000001.jpg", b"fake-jpg-1")
            archive.writestr("slide_000002.jpeg", b"fake-jpg-2")

        response = client.get(f"/jobs/{job_id}/artifacts/keyframes-zip")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/zip"
        assert "attachment; filename=" in response.headers.get("content-disposition", "")

        archive_path = tmp_path / "bundle.zip"
        archive_path.write_bytes(response.content)
        with zipfile.ZipFile(archive_path) as archive:
            names = sorted(archive.namelist())
        assert names == ["slide_000001.jpg", "slide_000002.jpeg"]


def test_runtime_keyframes_zip_route_returns_not_found_when_missing(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        response = client.get(f"/jobs/{job_id}/artifacts/keyframes-zip")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_runtime_keyframes_zip_route_returns_not_found_when_images_dir_empty(
    tmp_path: Path,
) -> None:
    with _make_client(tmp_path) as client:
        created_project = client.post("/projects", json={"title": "demo"})
        project_id = created_project.json()["project_id"]
        created_job = client.post("/jobs", json={"project_id": project_id})
        job_id = created_job.json()["job_id"]

        images_dir = (
            tmp_path / "runtime" / "workspaces" / project_id / "jobs" / job_id / "frames" / "images"
        )
        images_dir.mkdir(parents=True, exist_ok=True)

        response = client.get(f"/jobs/{job_id}/artifacts/keyframes-zip")
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


@pytest.mark.parametrize("raw_cursor", ["-1", "not-an-integer", "999999"])
def test_runtime_ws_rejects_invalid_cursor_and_cleans_connection(
    tmp_path: Path,
    raw_cursor: str,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    with _make_client(tmp_path) as client:
        project_id = client.post("/projects", json={"title": "demo"}).json()["project_id"]
        job_id = client.post("/jobs", json={"project_id": project_id}).json()["job_id"]

        with client.websocket_connect(f"/ws/jobs/{job_id}?after_cursor={raw_cursor}") as websocket:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()

        assert exc_info.value.code == 4400
        runtime = cast(Any, client.app).state.runtime
        assert job_id not in runtime.ws_gateway._connections
        assert job_id not in runtime.ws_gateway._subscriptions


def test_runtime_ws_missing_job_closes_without_leaking_subscription(tmp_path: Path) -> None:
    from starlette.websockets import WebSocketDisconnect

    with _make_client(tmp_path) as client:
        with client.websocket_connect("/ws/jobs/j_missing") as websocket:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()

        assert exc_info.value.code == 4404
        runtime = cast(Any, client.app).state.runtime
        assert "j_missing" not in runtime.ws_gateway._connections
        assert "j_missing" not in runtime.ws_gateway._subscriptions
        assert "j_missing" not in runtime.control_plane._subscriptions


def test_runtime_ws_control_ack_uses_versioned_envelope_and_request_id(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        project_id = client.post("/projects", json={"title": "demo"}).json()["project_id"]
        job_id = client.post("/jobs", json={"project_id": project_id}).json()["job_id"]
        claim_repository = SQLiteJobRepository(tmp_path / "runtime" / "infra.db")
        try:
            claimed = claim_repository.claim_next_job("runtime-test-worker")
            assert claimed is not None
        finally:
            claim_repository.close()

        with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            snapshot = ws.receive_json()
            assert snapshot["event_type"] == "snapshot"
            ws.send_json({"command": "pause", "request_id": "runtime-command-1"})
            control_ack = ws.receive_json()

        assert control_ack["event_type"] == "control_ack"
        assert control_ack["request_id"] == "runtime-command-1"
        assert isinstance(control_ack["cursor"], int)
        assert isinstance(control_ack["state_version"], int)
        assert control_ack["payload"]["confirmed"] is False


def test_runtime_startup_fails_when_app_secret_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from apps.api.service import ApiConfigError
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_in_memory=True)
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


def test_runtime_cookie_validate_marks_invalid_on_decrypt_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

        monkeypatch.setenv("APP_SECRET_KEY", "different-secret")
        response = client.post(
            f"/me/cookies/{cookie_id}/validate",
            json={"source_url": "https://www.bilibili.com/video/BV1demo"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "invalid"
        assert payload["last_error_code"] == "cookie_decrypt_failed"

        listed = client.get("/me/cookies")
        assert listed.status_code == 200
        rows = listed.json()
        assert any(row["id"] == cookie_id and row["status"] == "invalid" for row in rows)


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


@pytest.mark.parametrize("override", [None, False, True])
def test_runtime_in_memory_event_bus_is_explicit_test_only_override(
    tmp_path: Path,
    override: bool | None,
) -> None:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_in_memory=override)
    with TestClient(app) as client:
        _ = client.get("/healthz")
        runtime = cast(Any, client.app).state.runtime
        if override is True:
            assert isinstance(runtime.event_bus, InMemoryEventBus)
        else:
            assert isinstance(runtime.event_bus, SQLiteEventBus)
