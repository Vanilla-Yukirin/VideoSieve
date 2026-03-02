from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from infra import FileSystemWorkspaceStore
from ingest import (
    INGEST_AUTH_REQUIRED,
    INGEST_CANCELLED,
    IngestAssetSelection,
    IngestError,
    IngestRequest,
    probe_url_formats,
    run_url_ingest,
)
from ingest import providers as ingest_providers


class _FakeDownloadError(Exception):
    pass


def _create_cookie_vault_db(db_path: Path, *, cookie_id: str, cookie_encrypted: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_cookies (
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
            """
        )
        conn.execute(
            """
            INSERT INTO user_cookies (
              id, user_id, name, cookie_encrypted, is_default, status,
              last_validated_at, last_error_code, created_at, updated_at
            ) VALUES (?, 'default_user', 'test', ?, 1, 'valid', NULL, NULL, 'now', 'now')
            """,
            (cookie_id, cookie_encrypted),
        )
        conn.commit()
    finally:
        conn.close()


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

    video_path = workspace.source_video_file("p_url_1", "j_url_1")
    meta_path = workspace.job_meta_file("p_url_1", "j_url_1")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))

    assert video_path.exists()
    assert video_path.read_bytes() == b"video-bytes"
    assert payload["source_ref"] == "https://www.bilibili.com/video/BV1abcd12345"
    assert payload["title"] == "Bili Demo"
    assert payload["source_type"] == "bilibili_url"
    assert payload["selected_format"] == "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[ext=mp4]/best"
    assert payload["dedupe_applied"] is True
    assert result.retry_count == 0


def test_run_url_ingest_uses_selected_format_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    observed_opts: dict[str, object] = {}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            observed_opts.update(self._opts)
            Path(str(self._opts["outtmpl"])).write_bytes(b"video-bytes")
            return {
                "title": "fmt test",
                "webpage_url": source_url,
                "requested_downloads": [
                    {"format_id": "30116", "vcodec": "avc1", "acodec": "none"},
                    {"format_id": "30280", "vcodec": "none", "acodec": "mp4a"},
                ],
            }

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_url_fmt",
        job_id="j_url_fmt",
        source_url="https://www.bilibili.com/video/BV1fmtfmtfmt",
        video_format_id="30116",
        audio_format_id="30280",
    )
    result = run_url_ingest(workspace, request)

    assert observed_opts["format"] == "30116+30280"
    assert result.meta.selected_video_format_id == "30116"
    assert result.meta.selected_audio_format_id == "30280"
    assert result.meta.analysis_selected_video_format_id == "30116"
    assert result.meta.analysis_selected_audio_format_id == "30280"
    assert result.meta.quality_selected_video_format_id == "30116"
    assert result.meta.quality_selected_audio_format_id == "30280"
    assert result.meta.dedupe_applied is True


def test_run_url_ingest_emits_progress_callback_with_eta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    progress_events: list[dict[str, object]] = []

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            hooks = self._opts.get("progress_hooks")
            assert isinstance(hooks, list)
            assert bool(self._opts.get("noprogress")) is True
            for hook in hooks:
                hook(
                    {
                        "status": "downloading",
                        "_percent_str": "57.6%",
                        "_speed_str": "10.55MiB/s",
                        "_eta_str": "00:52",
                    }
                )
            Path(str(self._opts["outtmpl"])).write_bytes(b"video-bytes")
            return {"title": "progress test", "webpage_url": source_url}

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_progress_1",
        job_id="j_progress_1",
        source_url="https://www.bilibili.com/video/BV1progress",
    )
    run_url_ingest(
        workspace, request, progress_callback=lambda payload: progress_events.append(payload)
    )

    assert progress_events
    first = progress_events[0]
    assert first["status"] == "downloading"
    assert first["percent"] == "57.6%"
    assert first["speed"] == "10.55MiB/s"
    assert first["eta"] == "00:52"


def test_run_url_ingest_dual_asset_plan_without_dedupe_downloads_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    downloads: list[tuple[str, str]] = []

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is True
            target = Path(str(self._opts["outtmpl"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(str(self._opts["format"]).encode("utf-8"))
            downloads.append((str(self._opts["format"]), target.name))
            return {
                "title": "dual plan",
                "webpage_url": source_url,
                "requested_downloads": [
                    {
                        "format_id": str(self._opts["format"]).split("+")[0],
                        "vcodec": "avc1",
                        "acodec": "none",
                    }
                ],
            }

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_dual_1",
        job_id="j_dual_1",
        source_url="https://www.bilibili.com/video/BV1dualaaaa",
        analysis_asset=IngestAssetSelection(video_format_id="30032", audio_format_id="30280"),
        quality_asset=IngestAssetSelection(video_format_id="30116", audio_format_id="30280"),
    )
    result = run_url_ingest(workspace, request)

    assert len(downloads) == 2
    assert ("30116+30280", "source.mp4") in downloads
    assert ("30032+30280", "source.analysis.mp4") in downloads
    assert workspace.source_video_file("p_dual_1", "j_dual_1").exists()
    assert workspace.job_path("p_dual_1", "j_dual_1", "media", "source.analysis.mp4").exists()
    assert result.meta.dedupe_applied is False
    assert result.meta.analysis_selected_video_format_id == "30032"
    assert result.meta.quality_selected_video_format_id == "30116"


def test_run_url_ingest_dual_asset_plan_with_dedupe_downloads_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    download_count = {"n": 0}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is True
            download_count["n"] += 1
            Path(str(self._opts["outtmpl"])).write_bytes(b"one")
            return {
                "title": "dedupe plan",
                "webpage_url": source_url,
            }

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_dual_2",
        job_id="j_dual_2",
        source_url="https://www.bilibili.com/video/BV1dualbbbb",
        analysis_asset=IngestAssetSelection(video_format_id="30064", audio_format_id="30280"),
        quality_asset=IngestAssetSelection(video_format_id="30064", audio_format_id="30280"),
    )
    result = run_url_ingest(workspace, request)

    assert download_count["n"] == 1
    assert workspace.source_video_file("p_dual_2", "j_dual_2").exists()
    assert not workspace.job_path("p_dual_2", "j_dual_2", "media", "source.analysis.mp4").exists()
    assert result.meta.dedupe_applied is True
    assert result.meta.analysis_selected_video_format_id == "30064"
    assert result.meta.quality_selected_video_format_id == "30064"


def test_run_url_ingest_can_interrupt_download_via_cancel_checker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    checker_calls = {"n": 0}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is True
            hooks = self._opts.get("progress_hooks")
            assert isinstance(hooks, list) and hooks
            hook = hooks[0]
            assert callable(hook)
            try:
                hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})
            except Exception as exc:
                raise _FakeDownloadError(str(exc)) from exc
            return {"title": "cancelled", "webpage_url": source_url}

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_cancel_1",
        job_id="j_cancel_1",
        source_url="https://www.bilibili.com/video/BV1cancelled",
    )

    def _cancel_checker() -> bool:
        checker_calls["n"] += 1
        return checker_calls["n"] >= 2

    with pytest.raises(IngestError) as exc_info:
        run_url_ingest(workspace, request, cancel_checker=_cancel_checker)
    assert exc_info.value.code == INGEST_CANCELLED
    assert checker_calls["n"] >= 2


def test_probe_url_formats_returns_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            assert download is False
            return {
                "title": "probe test",
                "uploader": "uploader-a",
                "duration": 12.3,
                "webpage_url": source_url,
                "formats": [
                    {
                        "format_id": "30116",
                        "ext": "mp4",
                        "resolution": "1920x1080",
                        "fps": 60,
                        "tbr": 1359,
                        "vcodec": "avc1",
                        "acodec": "none",
                    },
                    {
                        "format_id": "30280",
                        "ext": "m4a",
                        "resolution": "audio only",
                        "tbr": 141,
                        "vcodec": "none",
                        "acodec": "mp4a",
                    },
                ],
            }

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_probe",
        job_id="j_probe",
        source_url="https://www.bilibili.com/video/BV1probeprobe",
    )
    probe = probe_url_formats(request)

    assert probe.title == "probe test"
    assert len(probe.formats) == 2
    assert probe.formats[0].format_id == "30116"
    assert probe.formats[1].is_audio_only is True


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


def test_run_url_ingest_cookie_id_uses_vault_cookie_and_cleans_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    cookie_db = tmp_path / "infra.db"
    cookie_text = "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tvault\n"
    _create_cookie_vault_db(
        cookie_db,
        cookie_id="c_ingest_ok",
        cookie_encrypted="enc-cookie-id",
    )
    monkeypatch.setenv("VIDEOSIEVE_COOKIE_VAULT_DB_PATH", str(cookie_db))
    monkeypatch.setattr(
        ingest_providers,
        "_decrypt_cookie_encrypted",
        lambda **kwargs: cookie_text,
    )

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
            assert "SESSDATA\tvault" in Path(cookie_path).read_text(encoding="utf-8")
            Path(str(self._opts["outtmpl"])).write_bytes(b"ok")
            return {"title": "Cookie ID Demo", "webpage_url": source_url}

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    fallback_cookie = tmp_path / "cookies.txt"
    fallback_cookie.write_text("SHOULD_NOT_BE_USED", encoding="utf-8")
    request = IngestRequest(
        project_id="p_cookie_id",
        job_id="j_cookie_id",
        source_url="https://www.bilibili.com/video/BV2cookieid",
        cookie_id="c_ingest_ok",
        cookie_file_path=str(fallback_cookie),
    )
    run_url_ingest(workspace, request)

    assert "path" in observed_cookiefile
    assert observed_cookiefile["path"] != str(fallback_cookie.resolve())
    assert not Path(observed_cookiefile["path"]).exists()


def test_run_url_ingest_cookie_secret_ref_missing_env_raises_auth_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    monkeypatch.delenv("VIDEOSIEVE_COOKIE_REF_BILI_PROD", raising=False)

    request = IngestRequest(
        project_id="p_cookie_ref",
        job_id="j_cookie_ref",
        source_url="https://www.bilibili.com/video/BV2cookieref",
        cookie_secret_ref="bili-prod",
    )
    with pytest.raises(IngestError) as error_info:
        run_url_ingest(workspace, request)

    assert error_info.value.code == INGEST_AUTH_REQUIRED
    assert "VIDEOSIEVE_COOKIE_REF_BILI_PROD" in error_info.value.message


def test_run_url_ingest_cookie_id_auth_failure_maps_to_auth_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    cookie_db = tmp_path / "infra.db"
    cookie_text = (
        "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\texpired\n"
    )
    _create_cookie_vault_db(
        cookie_db,
        cookie_id="c_ingest_expired",
        cookie_encrypted="enc-cookie-auth",
    )
    monkeypatch.setenv("VIDEOSIEVE_COOKIE_VAULT_DB_PATH", str(cookie_db))
    monkeypatch.setattr(
        ingest_providers,
        "_decrypt_cookie_encrypted",
        lambda **kwargs: cookie_text,
    )

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            raise _FakeDownloadError("Sign in to confirm your age")

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_cookie_auth",
        job_id="j_cookie_auth",
        source_url="https://www.bilibili.com/video/BV2cookieauth",
        cookie_id="c_ingest_expired",
        download_retries=1,
    )

    with pytest.raises(IngestError) as error_info:
        run_url_ingest(workspace, request)
    assert error_info.value.code == INGEST_AUTH_REQUIRED


def test_run_url_ingest_cookie_id_error_path_cleans_temp_cookie_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    cookie_db = tmp_path / "infra.db"
    cookie_text = (
        "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tcleanup\n"
    )
    _create_cookie_vault_db(
        cookie_db,
        cookie_id="c_ingest_cleanup",
        cookie_encrypted="enc-cookie-cleanup",
    )
    monkeypatch.setenv("VIDEOSIEVE_COOKIE_VAULT_DB_PATH", str(cookie_db))
    monkeypatch.setattr(
        ingest_providers,
        "_decrypt_cookie_encrypted",
        lambda **kwargs: cookie_text,
    )

    observed_cookiefile: dict[str, str] = {}

    class _FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._opts = opts

        def __enter__(self) -> _FakeYoutubeDL:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def extract_info(self, source_url: str, *, download: bool) -> dict[str, object]:
            observed_cookiefile["path"] = str(self._opts["cookiefile"])
            raise _FakeDownloadError("HTTP Error 403: Forbidden")

    fake_module = SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setattr(ingest_providers, "_load_yt_dlp", lambda: (fake_module, _FakeDownloadError))

    request = IngestRequest(
        project_id="p_cookie_cleanup",
        job_id="j_cookie_cleanup",
        source_url="https://www.bilibili.com/video/BV2cookiecleanup",
        cookie_id="c_ingest_cleanup",
        download_retries=0,
    )

    with pytest.raises(IngestError):
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
