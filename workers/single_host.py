"""Durable single-host worker backed by SQLite and the local workspace."""

from __future__ import annotations

import argparse
import importlib
import os
import socket
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta
from io import BufferedRandom
from pathlib import Path

from dotenv import load_dotenv

from asr import create_asr_provider_from_config
from contracts import JobStatus, StageName
from infra import (
    FileSystemWorkspaceStore,
    InfraEvent,
    JobRecord,
    SQLiteEventBus,
    SQLiteJobRepository,
)
from pipeline import PipelineOrchestrator
from pipeline.dispatch import extract_ingest_config, load_job_config_snapshot

from .runtime import WorkerRuntime


class WorkerAlreadyRunningError(RuntimeError):
    """Raised when another worker process owns the single-host lock."""


class _SingleInstanceLock:
    """Cross-platform advisory lock for the worker CLI process."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: BufferedRandom | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise WorkerAlreadyRunningError(
                f"another VideoSieve worker owns {self._path}"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> _SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class _HeartbeatLease:
    def __init__(
        self,
        *,
        db_path: Path,
        job_id: str,
        worker_id: str,
        worker_attempt: int,
        interval_seconds: float,
    ) -> None:
        self._db_path = db_path
        self._job_id = job_id
        self._worker_id = worker_id
        self._worker_attempt = worker_attempt
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"videosieve-heartbeat-{job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self._interval_seconds * 2))

    def _run(self) -> None:
        repository = SQLiteJobRepository(self._db_path)
        try:
            while not self._stop.wait(self._interval_seconds):
                if not repository.heartbeat_job(
                    self._job_id,
                    self._worker_id,
                    expected_attempt=self._worker_attempt,
                ):
                    return
        finally:
            repository.close()


class SingleHostWorker:
    """Claim and execute durable jobs one at a time on a single host."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 5.0,
        stale_after_seconds: float = 30.0,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "infra.db"
        self._repository = SQLiteJobRepository(self._db_path)
        self._repository.ensure_schema()
        self._workspace = FileSystemWorkspaceStore(self._data_dir / "workspaces")
        self._event_bus = SQLiteEventBus(self._db_path)
        self._worker_id = worker_id or _default_worker_id()
        self._poll_interval_seconds = max(0.05, poll_interval_seconds)
        self._heartbeat_interval_seconds = max(0.1, heartbeat_interval_seconds)
        self._stale_after_seconds = max(
            self._heartbeat_interval_seconds * 2,
            stale_after_seconds,
        )
        self._stop = threading.Event()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def run_once(self) -> bool:
        """Claim and execute at most one job; return whether a job was claimed."""

        self._interrupt_stale_claims()
        job = self._repository.claim_next_job(self._worker_id)
        if job is None:
            return False

        lease = _HeartbeatLease(
            db_path=self._db_path,
            job_id=job.job_id,
            worker_id=self._worker_id,
            worker_attempt=job.attempt,
            interval_seconds=self._heartbeat_interval_seconds,
        )
        lease.start()
        try:
            self._event_bus.publish(
                f"jobs:{job.job_id}",
                InfraEvent(
                    event_type="job_state_changed",
                    project_id=job.project_id,
                    job_id=job.job_id,
                    payload={
                        "from": (
                            JobStatus.PAUSED.value
                            if job.control_command == "resume"
                            else JobStatus.QUEUED.value
                        ),
                        "to": JobStatus.RUNNING.value,
                        "stage": job.stage,
                    },
                ),
            )

            if (
                job.control_command == "resume"
                and job.control_version > 0
                and job.control_ack_version == job.control_version
            ):
                self._event_bus.publish(
                    f"jobs:{job.job_id}",
                    InfraEvent(
                        event_type="control_ack",
                        project_id=job.project_id,
                        job_id=job.job_id,
                        payload={
                            "command": "resume",
                            "accepted": True,
                            "phase": "applied",
                            "confirmed": True,
                            "control_version": job.control_version,
                            "execution_state": JobStatus.RUNNING.value,
                            "requested_action": None,
                        },
                        request_id=job.control_request_id,
                    ),
                )
            self._run_claimed_job(job.project_id, job.job_id, job.attempt)
        except Exception as exc:
            self._handle_claim_failure(job, exc)
        finally:
            lease.stop()
            released = self._repository.release_job_claim(
                job.job_id,
                self._worker_id,
                expected_attempt=job.attempt,
            )
            if released:
                latest = self._repository.get_job(job.job_id)
                if latest is not None:
                    self._publish_best_effort(
                        f"jobs:{job.job_id}",
                        InfraEvent(
                            event_type="job_state_changed",
                            project_id=job.project_id,
                            job_id=job.job_id,
                            payload={
                                "from": latest.status,
                                "to": latest.status,
                                "stage": latest.stage,
                                "worker_released": True,
                            },
                        ),
                    )
        return True

    def run_forever(self) -> None:
        """Poll the durable queue until ``stop`` is requested."""

        while not self._stop.is_set():
            try:
                if self.run_once():
                    continue
            except Exception as exc:
                print(
                    f"VideoSieve worker poll failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
            self._stop.wait(self._poll_interval_seconds)

    def _handle_claim_failure(self, job: JobRecord, exc: Exception) -> None:
        job_id = job.job_id
        project_id = job.project_id
        attempt = job.attempt
        latest = self._repository.get_job(job_id)
        if latest is None or latest.status in {
            JobStatus.PAUSED.value,
            JobStatus.CANCELLED.value,
            JobStatus.FAILED.value,
            JobStatus.SUCCEEDED.value,
            JobStatus.INTERRUPTED.value,
        }:
            return
        message = str(exc) or exc.__class__.__name__
        error_code = str(getattr(exc, "code", "WORKER_EXECUTION_FAILED"))
        updated = self._repository.update_job_status(
            job_id,
            status=JobStatus.FAILED.value,
            stage=latest.stage,
            error_code=error_code,
            error_message=message,
            expected_worker_id=self._worker_id,
            expected_attempt=attempt,
        )
        if not updated:
            return
        self._repository.refresh_project_status(project_id)
        self._publish_best_effort(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="job_state_changed",
                project_id=project_id,
                job_id=job_id,
                payload={
                    "from": latest.status,
                    "to": JobStatus.FAILED.value,
                    "stage": latest.stage,
                },
            ),
        )
        self._publish_best_effort(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="error",
                project_id=project_id,
                job_id=job_id,
                payload={
                    "stage": latest.stage or "dispatch",
                    "code": error_code,
                    "message": message,
                },
            ),
        )

    def _publish_best_effort(self, channel: str, event: InfraEvent) -> None:
        try:
            self._event_bus.publish(channel, event)
        except Exception as exc:
            print(
                f"VideoSieve worker event publish failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self.stop()
        self._event_bus.close()
        self._repository.close()

    def _run_claimed_job(self, project_id: str, job_id: str, worker_attempt: int) -> None:
        snapshot = load_job_config_snapshot(
            self._workspace,
            project_id=project_id,
            job_id=job_id,
        )
        ingest_config = extract_ingest_config(snapshot)
        local_video_path = _optional_str(snapshot.get("local_video_path"))
        local_video_context = _optional_str(snapshot.get("local_video_context")) or ""
        if local_video_path and not ingest_config:
            ingest_config = {"source_path": local_video_path}
        raw_asr_config = snapshot.get("asr")
        asr_config = raw_asr_config if isinstance(raw_asr_config, dict) else {}

        runtime = WorkerRuntime(
            PipelineOrchestrator(
                repository=self._repository,
                workspace=self._workspace,
                event_bus=self._event_bus,
                asr_provider=create_asr_provider_from_config(asr_config),
                worker_id=self._worker_id,
                worker_attempt=worker_attempt,
            )
        )
        rerun_from_stage = _optional_stage(snapshot.get("rerun_from_stage"))
        runtime.run_job(
            project_id=project_id,
            job_id=job_id,
            source_path=local_video_path,
            ingest_config=ingest_config,
            rerun_from_stage=rerun_from_stage,
            title=_optional_str(snapshot.get("title")),
            description=_optional_str(snapshot.get("description")) or local_video_context,
            tags=_str_list(snapshot.get("tags")),
            language_hint=_optional_str(snapshot.get("language_hint")),
            duration_seconds=_positive_float(snapshot.get("duration_seconds"), default=30.0),
        )

    def _interrupt_stale_claims(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self._stale_after_seconds)
        interrupted = self._repository.mark_stale_jobs_interrupted(cutoff)
        for job_id in interrupted:
            job = self._repository.get_job(job_id)
            if job is None:
                continue
            self._event_bus.publish(
                f"jobs:{job_id}",
                InfraEvent(
                    event_type="job_state_changed",
                    project_id=job.project_id,
                    job_id=job_id,
                    payload={
                        "from": JobStatus.RUNNING.value,
                        "to": JobStatus.INTERRUPTED.value,
                        "stage": job.stage,
                    },
                ),
            )
            self._event_bus.publish(
                f"jobs:{job_id}",
                InfraEvent(
                    event_type="error",
                    project_id=job.project_id,
                    job_id=job_id,
                    payload={
                        "stage": job.stage or "worker",
                        "code": "WORKER_HEARTBEAT_EXPIRED",
                        "message": "worker heartbeat expired; explicit resume is required",
                    },
                ),
            )


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_stage(value: object) -> StageName | None:
    text = _optional_str(value)
    return StageName(text) if text is not None else None


def _positive_float(value: object, *, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    if not isinstance(value, str | int | float):
        return default
    parsed = float(value)
    return parsed if parsed > 0 else default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the VideoSieve single-host worker")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.local"),
        help="Load worker credentials and defaults from this file when it exists",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
    )
    parser.add_argument("--worker-id")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--heartbeat-interval", type=float, default=5.0)
    parser.add_argument("--stale-after", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)
    data_dir = args.data_dir or Path(os.getenv("VIDEOSIEVE_API_DATA_DIR", "runtime/api"))

    try:
        with _SingleInstanceLock(data_dir / "worker.lock"):
            worker = SingleHostWorker(
                data_dir,
                worker_id=args.worker_id,
                poll_interval_seconds=args.poll_interval,
                heartbeat_interval_seconds=args.heartbeat_interval,
                stale_after_seconds=args.stale_after,
            )
            try:
                if args.once:
                    worker.run_once()
                else:
                    worker.run_forever()
            except KeyboardInterrupt:
                worker.stop()
            finally:
                worker.close()
    except WorkerAlreadyRunningError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
