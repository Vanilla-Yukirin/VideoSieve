from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from infra import FileSystemWorkspaceStore
from ingest import (
    INGEST_AUTH_REQUIRED,
    IngestAssetSelection,
    IngestError,
    IngestRequest,
    probe_url_formats,
    run_url_ingest,
)
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
    assert workspace.source_video_file("p_dual_1").exists()
    assert workspace.path("p_dual_1", "media", "source.analysis.mp4").exists()
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
    assert workspace.source_video_file("p_dual_2").exists()
    assert not workspace.path("p_dual_2", "media", "source.analysis.mp4").exists()
    assert result.meta.dedupe_applied is True
    assert result.meta.analysis_selected_video_format_id == "30064"
    assert result.meta.quality_selected_video_format_id == "30064"


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
