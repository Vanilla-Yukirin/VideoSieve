from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

from infra import SQLiteJobRepository


def _queued_job(db_path: Path, *, job_id: str = "job-1") -> None:
    repository = SQLiteJobRepository(db_path)
    repository.ensure_schema()
    repository.upsert_project("project-1", title="demo", status="queued")
    repository.create_job(job_id, "project-1", status="queued", stage="ingest")
    repository.close()


def test_two_workers_cannot_claim_the_same_job(tmp_path: Path) -> None:
    db_path = tmp_path / "infra.db"
    _queued_job(db_path)
    ready = Barrier(2)

    def claim(worker_id: str) -> str | None:
        repository = SQLiteJobRepository(db_path)
        repository.ensure_schema()
        ready.wait(timeout=5)
        claimed = repository.claim_next_job(worker_id)
        repository.close()
        return claimed.job_id if claimed is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed_ids = list(pool.map(claim, ("worker-a", "worker-b")))

    assert claimed_ids.count("job-1") == 1
    assert claimed_ids.count(None) == 1


def test_control_request_is_distinct_from_worker_acknowledgement(tmp_path: Path) -> None:
    db_path = tmp_path / "infra.db"
    _queued_job(db_path)
    repository = SQLiteJobRepository(db_path)

    claimed = repository.claim_next_job("worker-a")
    assert claimed is not None
    assert claimed.status == "running"

    control_version = repository.request_job_control("job-1", "pause")
    requested = repository.get_job("job-1")
    assert requested is not None
    assert requested.status == "running"
    assert requested.status not in {"pause_requested", "cancel_requested"}
    assert requested.control_command == "pause"
    assert requested.control_version == control_version
    assert requested.control_ack_version < control_version
    assert requested.control_requested_at is not None
    assert requested.control_acknowledged_at is None

    assert (
        repository.acknowledge_job_control(
            "job-1",
            "different-worker",
            control_version,
        )
        is False
    )
    assert repository.acknowledge_job_control("job-1", "worker-a", control_version) is True

    acknowledged = repository.get_job("job-1")
    assert acknowledged is not None
    assert acknowledged.status == "running"
    assert acknowledged.status not in {"pause_requested", "cancel_requested"}
    assert acknowledged.control_ack_version == control_version
    assert acknowledged.control_acknowledged_at is not None
    repository.close()


def test_stale_claim_requires_explicit_recovery_before_another_worker_can_claim(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "infra.db"
    _queued_job(db_path)

    first_process = SQLiteJobRepository(db_path)
    first_claim = first_process.claim_next_job("worker-before-crash")
    assert first_claim is not None
    assert first_claim.attempt == 1
    first_process.close()

    api_after_restart = SQLiteJobRepository(db_path)
    api_after_restart.ensure_schema()
    stale_before = datetime.now(UTC) + timedelta(seconds=1)
    assert api_after_restart.mark_stale_jobs_interrupted(stale_before) == ["job-1"]

    interrupted = api_after_restart.get_job("job-1")
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.worker_id is None
    assert interrupted.attempt == 1
    assert api_after_restart.claim_next_job("worker-too-early") is None

    assert api_after_restart.recover_interrupted_job("job-1") is True
    recovered = api_after_restart.get_job("job-1")
    assert recovered is not None
    assert recovered.status == "queued"

    second_claim = api_after_restart.claim_next_job("worker-after-recovery")
    assert second_claim is not None
    assert second_claim.job_id == "job-1"
    assert second_claim.worker_id == "worker-after-recovery"
    assert second_claim.attempt == 2
    api_after_restart.close()
