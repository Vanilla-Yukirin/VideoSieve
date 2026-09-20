from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from infra import SQLiteJobRepository

_CLAIM_SCRIPT = """
import json
import sys
from infra import SQLiteJobRepository

repository = SQLiteJobRepository(sys.argv[1])
repository.ensure_schema()
record = repository.claim_next_job(sys.argv[2])
repository.close()
print(json.dumps(None if record is None else {
    "job_id": record.job_id,
    "worker_id": record.worker_id,
    "attempt": record.attempt,
}))
"""


def _child_env() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    package_path = str(root / "packages")
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = package_path if not previous else package_path + os.pathsep + previous
    return env


def _create_queued_job(db_path: Path) -> None:
    repository = SQLiteJobRepository(db_path)
    repository.ensure_schema()
    repository.upsert_project("project-1", title="demo", status="queued")
    repository.create_job("job-1", "project-1", status="queued", stage="ingest")
    repository.close()


def _run_claim(db_path: Path, worker_id: str) -> dict[str, object] | None:
    completed = subprocess.run(
        [sys.executable, "-c", _CLAIM_SCRIPT, str(db_path), worker_id],
        check=False,
        capture_output=True,
        text=True,
        env=_child_env(),
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    decoded = json.loads(completed.stdout)
    if decoded is None:
        return None
    return cast(dict[str, object], decoded)


def test_atomic_claim_holds_across_independent_processes(tmp_path: Path) -> None:
    db_path = tmp_path / "infra.db"
    _create_queued_job(db_path)
    env = _child_env()

    children = [
        subprocess.Popen(
            [sys.executable, "-c", _CLAIM_SCRIPT, str(db_path), worker_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for worker_id in ("process-a", "process-b")
    ]
    outputs = [child.communicate(timeout=15) for child in children]

    for child, (_, stderr) in zip(children, outputs, strict=True):
        assert child.returncode == 0, stderr
    claims = [json.loads(stdout) for stdout, _ in outputs]
    successful = [claim for claim in claims if claim is not None]
    assert len(successful) == 1
    assert successful[0]["job_id"] == "job-1"
    assert successful[0]["attempt"] == 1


def test_crashed_process_claim_is_persisted_and_explicitly_recovered(tmp_path: Path) -> None:
    db_path = tmp_path / "infra.db"
    _create_queued_job(db_path)

    first = _run_claim(db_path, "process-before-crash")
    assert first == {
        "job_id": "job-1",
        "worker_id": "process-before-crash",
        "attempt": 1,
    }

    restarted_api = SQLiteJobRepository(db_path)
    restarted_api.ensure_schema()
    stale_before = datetime.now(UTC) + timedelta(seconds=1)
    assert restarted_api.mark_stale_jobs_interrupted(stale_before) == ["job-1"]
    interrupted = restarted_api.get_job("job-1")
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert restarted_api.recover_interrupted_job("job-1") is True
    restarted_api.close()

    second = _run_claim(db_path, "process-after-restart")
    assert second == {
        "job_id": "job-1",
        "worker_id": "process-after-restart",
        "attempt": 2,
    }
