from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from scripts.run_local import (
    LocalRunError,
    _log,
    load_and_validate_env,
    port_is_available,
    validate_node_version,
    web_build_is_stale,
    web_dependencies_need_install,
)


def test_load_and_validate_env_accepts_local_api_origin(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "APP_SECRET_KEY=a-real-local-secret\n"
        "NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000\n",
        encoding="utf-8",
    )

    values = load_and_validate_env(env_file, api_port=8000)

    assert values["APP_SECRET_KEY"] == "a-real-local-secret"


@pytest.mark.parametrize(
    "content, message",
    [
        ("NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000\n", "APP_SECRET_KEY"),
        (
            "APP_SECRET_KEY=change-me-in-local-or-production\n"
            "NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000\n",
            "example value",
        ),
        (
            "APP_SECRET_KEY=valid\nNEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8123\n",
            "does not match",
        ),
        (
            "APP_SECRET_KEY=valid\nNEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:not-a-port\n",
            "is invalid",
        ),
    ],
)
def test_load_and_validate_env_rejects_invalid_startup_config(
    tmp_path: Path, content: str, message: str
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(content, encoding="utf-8")

    with pytest.raises(LocalRunError, match=message):
        load_and_validate_env(env_file, api_port=8000)


def test_port_is_available_reports_an_existing_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        assert port_is_available("127.0.0.1", port) is False


def test_validate_node_version_enforces_documented_minimum() -> None:
    assert validate_node_version("v20.9.0") == (20, 9, 0)

    with pytest.raises(LocalRunError, match="20.9.0 or newer"):
        validate_node_version("v18.20.0")


def test_log_replaces_characters_unsupported_by_console_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AsciiConsole:
        encoding = "ascii"

        def __init__(self) -> None:
            self.value = ""

        def write(self, value: str) -> int:
            value.encode(self.encoding)
            self.value += value
            return len(value)

        def flush(self) -> None:
            pass

    console = AsciiConsole()
    monkeypatch.setattr("sys.stdout", console)

    _log("Next.js ✓ ready", source="web")

    assert console.value == "[web] Next.js ? ready\n"


def test_web_dependency_check_requires_next_install(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    assert web_dependencies_need_install(tmp_path) is True

    next_entry = tmp_path / "node_modules" / "next" / "dist" / "bin" / "next"
    next_entry.parent.mkdir(parents=True)
    next_entry.write_text("", encoding="utf-8")
    marker = tmp_path / "node_modules" / ".package-lock.json"
    marker.write_text("{}", encoding="utf-8")
    future = max(path.stat().st_mtime for path in (next_entry, marker)) + 2
    os.utime(marker, (future, future))

    assert web_dependencies_need_install(tmp_path) is False


def test_web_build_check_detects_source_changes(tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    source_dir = web_dir / "app"
    source_dir.mkdir(parents=True)
    source = source_dir / "page.tsx"
    source.write_text("export default null", encoding="utf-8")
    marker = web_dir / ".next" / "BUILD_ID"
    marker.parent.mkdir()
    marker.write_text("build", encoding="utf-8")
    env_file = tmp_path / ".env.local"
    env_file.write_text("APP_SECRET_KEY=test", encoding="utf-8")
    marker_time = max(source.stat().st_mtime, env_file.stat().st_mtime) + 2
    os.utime(marker, (marker_time, marker_time))

    assert web_build_is_stale(env_file=env_file, web_dir=web_dir) is False

    changed_time = marker_time + 2
    os.utime(source, (changed_time, changed_time))

    assert web_build_is_stale(env_file=env_file, web_dir=web_dir) is True
