from __future__ import annotations

from pathlib import Path

import pytest
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
