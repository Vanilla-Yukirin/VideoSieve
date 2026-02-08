from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from infra import FileSystemWorkspaceStore
from ingest import INGEST_AUTH_REQUIRED, IngestError, IngestRequest, run_url_ingest
from ingest import providers as ingest_providers


class _FakeDownloadError(Exception):
    pass


def test_run_url_ingest_uses_ytdlp_and_writes_workspace_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is True
            assert source_url == "https://www.bilibili.com/video/BV1abcd12345"
            output_file = Path(str(self._opts["outtmpl"]))
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video-bytes")
            return {
                "title": "Bili Demo",
                "description": "Demo intro",
                "tags": ["AI", "Video"],
                "uploader": "demo-up",
                "duration": 123.4,
                "webpage_url": source_url,
            }

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(
        ingest_providers,
        "_load_yt_dlp",
        lambda: (fake_module, _FakeDownloadError),
    )

    request = IngestRequest(
        project_id="p_url_1",
        job_id="j_url_1",
        source_url="https://www.bilibili.com/video/BV1abcd12345",
        download_retries=2,
    )
    result = run_url_ingest(workspace, request)

    video_path = workspace.source_video_file("p_url_1")
    meta_path = workspace.meta_file("p_url_1")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))

    assert video_path.exists()
    assert video_path.read_bytes() == b"video-bytes"
    assert payload["source_ref"] == "https://www.bilibili.com/video/BV1abcd12345"
    assert payload["title"] == "Bili Demo"
    assert payload["source_type"] == "bilibili_url"
    assert result.retry_count == 0


def test_run_url_ingest_cookie_content_uses_temp_cookie_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    observed_cookiefile: dict[str, str] = {}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is True
            cookie_path = str(self._opts["cookiefile"])
            observed_cookiefile["path"] = cookie_path
            assert Path(cookie_path).read_text(encoding="utf-8").startswith("# Netscape")
            Path(str(self._opts["outtmpl"])).write_bytes(b"ok")
            return {"title": "Cookie Demo", "webpage_url": source_url}

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_url_2",
        job_id="j_url_2",
        source_url="https://www.bilibili.com/video/BV2abcd23456",
        cookie_content=(
            "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tdemo\n"
        ),
    )
    run_url_ingest(workspace, request)
    assert "path" in observed_cookiefile
    assert not Path(observed_cookiefile["path"]).exists()


def test_run_url_ingest_maps_auth_error_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    attempts = {"count": 0}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            attempts["count"] += 1
            raise _FakeDownloadError("Sign in to confirm your age")

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_url_3",
        job_id="j_url_3",
        source_url="https://www.bilibili.com/video/BV3abcd34567",
        download_retries=1,
    )
    with pytest.raises(IngestError) as error_info:
        run_url_ingest(workspace, request)

    assert attempts["count"] == 1
    assert error_info.value.code == INGEST_AUTH_REQUIRED


def test_run_url_ingest_retries_retryable_download_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    attempts = {"count": 0}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            attempts["count"] += 1
            raise _FakeDownloadError("HTTP Error 403: Forbidden")

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_url_4",
        job_id="j_url_4",
        source_url="https://example.com/video/demo",
        download_retries=2,
    )
    with pytest.raises(IngestError):
        run_url_ingest(workspace, request)

    assert attempts["count"] == 3
