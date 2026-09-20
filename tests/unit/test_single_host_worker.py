from __future__ import annotations

import os
from pathlib import Path

import pytest
from workers import single_host
from workers.single_host import WorkerAlreadyRunningError, _SingleInstanceLock


def test_worker_cli_lock_rejects_a_second_process_owner(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    first = _SingleInstanceLock(lock_path)
    second = _SingleInstanceLock(lock_path)

    first.acquire()
    try:
        with pytest.raises(WorkerAlreadyRunningError):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_worker_cli_loads_env_file_before_resolving_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "shared-runtime"
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        f"VIDEOSIEVE_API_DATA_DIR={data_dir.as_posix()}\nCAPSWRITER_TOKEN=test-token\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("VIDEOSIEVE_API_DATA_DIR", raising=False)
    monkeypatch.delenv("CAPSWRITER_TOKEN", raising=False)

    captured: dict[str, object] = {}

    class FakeLock:
        def __init__(self, path: Path) -> None:
            captured["lock_path"] = path

        def __enter__(self) -> FakeLock:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class FakeWorker:
        def __init__(self, worker_data_dir: Path, **_kwargs: object) -> None:
            captured["data_dir"] = worker_data_dir

        def run_once(self) -> None:
            captured["ran_once"] = True

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(single_host, "_SingleInstanceLock", FakeLock)
    monkeypatch.setattr(single_host, "SingleHostWorker", FakeWorker)

    assert single_host.main(["--env-file", str(env_file), "--once"]) == 0
    assert captured["data_dir"] == data_dir
    assert captured["lock_path"] == data_dir / "worker.lock"
    assert captured["ran_once"] is True
    assert captured["closed"] is True
    assert os.environ["CAPSWRITER_TOKEN"] == "test-token"
