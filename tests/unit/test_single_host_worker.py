from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from workers import single_host
from workers.single_host import (
    ProviderSecretResolutionError,
    SingleHostWorker,
    WorkerAlreadyRunningError,
    _resolve_provider_secret,
    _SingleInstanceLock,
)

from infra import SQLiteJobRepository, encrypt_secret


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


def test_provider_secret_resolution_uses_refs_and_only_old_snapshots_use_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "worker-secret")
    monkeypatch.setenv("QWEN_API_KEY", "legacy-env-key")
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    repository.create_provider_secret(
        secret_id="s-vlm",
        kind="vlm_api_key",
        secret_encrypted=encrypt_secret("database-key"),
    )

    assert (
        _resolve_provider_secret(
            repository,
            {},
            kind="vlm_api_key",
            fallback_env="QWEN_API_KEY",
        )
        == "legacy-env-key"
    )
    assert (
        _resolve_provider_secret(
            repository,
            {"credential_ref": None},
            kind="vlm_api_key",
            fallback_env="QWEN_API_KEY",
        )
        is None
    )
    assert (
        _resolve_provider_secret(
            repository,
            {"credential_ref": "s-vlm"},
            kind="vlm_api_key",
            fallback_env="QWEN_API_KEY",
        )
        == "database-key"
    )
    with pytest.raises(ProviderSecretResolutionError) as exc_info:
        _resolve_provider_secret(
            repository,
            {"credential_ref": "s-vlm"},
            kind="summary_api_key",
            fallback_env="SUMMARY_API_KEY",
        )
    assert exc_info.value.code == "PROVIDER_SECRET_REF_INVALID"
    repository.close()


def test_worker_injects_resolved_provider_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "worker-secret")
    worker = SingleHostWorker(tmp_path)
    refs: dict[str, str] = {}
    for kind, plaintext in (
        ("capswriter_token", "asr-db-token"),
        ("vlm_api_key", "vlm-db-key"),
        ("summary_api_key", "summary-db-key"),
    ):
        secret_id = f"s-{kind}"
        worker._repository.create_provider_secret(
            secret_id=secret_id,
            kind=kind,
            secret_encrypted=encrypt_secret(plaintext),
        )
        refs[kind] = secret_id

    project_id = "p-provider"
    job_id = "j-provider"
    worker._workspace.ensure_job_layout(project_id, job_id)
    worker._workspace.config_snapshot_file(project_id, job_id).write_text(
        json.dumps(
            {
                "asr": {
                    "provider": "capswriter",
                    "endpoint": "ws://localhost:6016",
                    "credential_ref": refs["capswriter_token"],
                },
                "frame_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "vlm",
                    "credential_ref": refs["vlm_api_key"],
                },
                "overall_summary": {
                    "base_url": "https://example.invalid/v1/chat/completions",
                    "model": "summary",
                    "credential_ref": refs["summary_api_key"],
                },
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_asr_factory(config: dict[str, object], *, token: str | None) -> object:
        captured["asr_config"] = config
        captured["asr_token"] = token
        return object()

    class FakeOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            captured["orchestrator"] = kwargs

    class FakeRuntime:
        def __init__(self, orchestrator: object) -> None:
            captured["runtime_orchestrator"] = orchestrator

        def run_job(self, **kwargs: object) -> None:
            captured["run_job"] = kwargs

    monkeypatch.setattr(single_host, "create_asr_provider_from_config", fake_asr_factory)
    monkeypatch.setattr(single_host, "PipelineOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(single_host, "WorkerRuntime", FakeRuntime)

    try:
        worker._run_claimed_job(project_id, job_id, 1)
    finally:
        worker.close()

    assert captured["asr_token"] == "asr-db-token"
    orchestrator_kwargs = captured["orchestrator"]
    assert isinstance(orchestrator_kwargs, dict)
    assert orchestrator_kwargs["frame_summary_api_key"] == "vlm-db-key"
    assert orchestrator_kwargs["summary_api_key"] == "summary-db-key"
    assert orchestrator_kwargs["allow_provider_env_fallback"] is False
