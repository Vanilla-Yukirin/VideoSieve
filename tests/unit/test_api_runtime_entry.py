from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest


def _make_client(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi")
    from apps.api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(data_dir=tmp_path / "runtime", event_bus_stub_mode=True)
    return TestClient(app)


def test_runtime_healthz_and_rest_smoke(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
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


def test_runtime_cookie_endpoint_returns_config_error_when_secret_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with _make_client(tmp_path) as client:
        response = client.post(
            "/me/cookies",
            json={
                "name": "demo",
                "cookie_netscape_text": (
                    "# Netscape HTTP Cookie File\n"
                    ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tdemo\n"
                ),
            },
        )
        assert response.status_code == 500
        assert response.json()["code"] == "config_error"


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


def test_runtime_probe_returns_config_error_when_secret_missing_with_cookie_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "runtime-secret")
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

        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        response = client.post(
            "/ingest/probe",
            json={
                "source_url": "https://www.bilibili.com/video/BV1demo",
                "cookie_id": cookie_id,
            },
        )
        assert response.status_code == 500
        assert response.json()["code"] == "config_error"


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
