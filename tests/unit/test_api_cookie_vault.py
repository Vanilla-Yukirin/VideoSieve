from __future__ import annotations

from pathlib import Path

import apps.api.service as api_service
import pytest
from apps.api.rest import (
    create_me_cookie,
    delete_me_cookie,
    list_me_cookies,
    patch_me_cookie,
    validate_me_cookie,
)
from apps.api.service import ApiConfigError, ApiControlPlane
from pydantic import ValidationError

from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository
from ingest import IngestFormatOption, IngestFormatProbeResult
from ingest.errors import INGEST_AUTH_REQUIRED, IngestError

COOKIE_TEXT = (
    "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tdemo\n"
)


@pytest.fixture(autouse=True)
def _default_app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")


def _make_control_plane(tmp_path: Path) -> ApiControlPlane:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    return ApiControlPlane(
        repository=repository,
        workspace=FileSystemWorkspaceStore(tmp_path / "workspaces"),
        event_bus=RedisEventBus(stub_mode=True),
        job_dispatcher=lambda _project_id, _job_id: None,
    )


def test_cookie_vault_crud_and_default_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "unit-secret")
    control_plane = _make_control_plane(tmp_path)

    first = create_me_cookie(
        control_plane,
        {"name": "primary", "cookie_netscape_text": COOKIE_TEXT, "is_default": True},
    )
    second = create_me_cookie(
        control_plane,
        {"name": "backup", "cookie_netscape_text": COOKIE_TEXT, "is_default": True},
    )

    rows = list_me_cookies(control_plane)
    assert len(rows) == 2
    assert rows[0]["is_default"] is False
    assert rows[1]["is_default"] is True
    assert "cookie_netscape_text" not in rows[0]
    assert "cookie_encrypted" not in rows[0]

    first_id = str(first["id"])
    second_id = str(second["id"])

    patched = patch_me_cookie(control_plane, first_id, {"name": "renamed"})
    assert patched["name"] == "renamed"

    deleted = delete_me_cookie(control_plane, second_id)
    assert deleted == {"deleted": True}
    remaining = list_me_cookies(control_plane)
    assert [item["id"] for item in remaining] == [first_id]


def test_cookie_vault_validate_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "unit-secret")
    control_plane = _make_control_plane(tmp_path)
    created = create_me_cookie(
        control_plane,
        {"name": "probe", "cookie_netscape_text": COOKIE_TEXT},
    )

    def _ok_probe(_request: object) -> IngestFormatProbeResult:
        return IngestFormatProbeResult(
            source_url="https://www.bilibili.com/video/BV1demo",
            title="demo",
            formats=[IngestFormatOption(format_id="18")],
        )

    monkeypatch.setattr(api_service, "probe_url_formats", _ok_probe)
    cookie_id = str(created["id"])

    ok = validate_me_cookie(
        control_plane,
        cookie_id,
        {"source_url": "https://www.bilibili.com/video/BV1demo"},
    )
    assert ok["status"] == "valid"
    assert ok["last_error_code"] is None

    def _bad_probe(_request: object) -> IngestFormatProbeResult:
        raise IngestError(
            code=INGEST_AUTH_REQUIRED,
            message="login required",
            retryable=False,
            context={"stage": "ingest"},
        )

    monkeypatch.setattr(api_service, "probe_url_formats", _bad_probe)
    bad = validate_me_cookie(
        control_plane,
        cookie_id,
        {"source_url": "https://www.bilibili.com/video/BV1demo"},
    )
    assert bad["status"] == "expired"
    assert bad["last_error_code"] == INGEST_AUTH_REQUIRED


def test_cookie_vault_validate_requires_source_url(tmp_path: Path) -> None:
    control_plane = _make_control_plane(tmp_path)
    created = create_me_cookie(
        control_plane,
        {"name": "probe", "cookie_netscape_text": COOKIE_TEXT},
    )
    cookie_id = str(created["id"])

    with pytest.raises(ValidationError):
        validate_me_cookie(control_plane, cookie_id, {})


def test_cookie_vault_validate_rejects_homepage_url(tmp_path: Path) -> None:
    control_plane = _make_control_plane(tmp_path)
    created = create_me_cookie(
        control_plane,
        {"name": "probe", "cookie_netscape_text": COOKIE_TEXT},
    )
    cookie_id = str(created["id"])

    with pytest.raises(ValidationError):
        validate_me_cookie(
            control_plane,
            cookie_id,
            {"source_url": "https://www.bilibili.com"},
        )


def test_cookie_vault_rejects_invalid_netscape_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "unit-secret")
    control_plane = _make_control_plane(tmp_path)

    with pytest.raises(ValueError):
        create_me_cookie(
            control_plane,
            {
                "name": "broken",
                "cookie_netscape_text": "just-text-without-tabs",
            },
        )


def test_cookie_vault_requires_app_secret_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with pytest.raises(ApiConfigError):
        _ = _make_control_plane(tmp_path)
