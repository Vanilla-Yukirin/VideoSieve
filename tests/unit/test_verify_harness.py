from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import verify


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_evidence(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"real-media-fixture")
    artifacts: dict[str, Path] = {}
    for section_name in ("asr", "frame_summary", "summary"):
        artifact = tmp_path / f"{section_name}.jsonl"
        artifact.write_text(f"real {section_name} output\n", encoding="utf-8")
        artifacts[section_name] = artifact

    run_id = "acceptance-20260920-001"
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "revision": "revision-1",
        "run_id": run_id,
        "recorded_at": "2026-09-20T00:00:00+08:00",
        "input": {
            "source": "local acceptance video",
            "artifact": str(source),
            "sha256": _sha256(source),
            "duration_seconds": 100.0,
        },
        "asr": {
            "provider": "capswriter",
            "model": "server-managed",
            "run_id": run_id,
            "artifact": str(artifacts["asr"]),
            "sha256": _sha256(artifacts["asr"]),
            "source_coverage_end_seconds": 99.0,
        },
        "frame_summary": {
            "provider": "qwen-frame-summary",
            "model": "qwen-vl-max",
            "request_id": "vlm-request-001",
            "artifact": str(artifacts["frame_summary"]),
            "sha256": _sha256(artifacts["frame_summary"]),
        },
        "summary": {
            "provider": "openai-compatible-summary",
            "model": "qwen-plus",
            "request_id": "llm-request-001",
            "artifact": str(artifacts["summary"]),
            "sha256": _sha256(artifacts["summary"]),
            "source_coverage_end_seconds": 99.0,
        },
        "human_review": {
            "transcript_content_and_timestamps": True,
            "frame_descriptions": True,
            "final_summary_fidelity": True,
        },
    }
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return evidence, payload


def _install_runtime_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "_probe_media_duration", lambda _path: 100.0)
    monkeypatch.setattr(
        verify,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="revision-1\n",
            stderr="",
        ),
    )


def _rewrite(evidence: Path, payload: dict[str, Any]) -> None:
    evidence.write_text(json.dumps(payload), encoding="utf-8")


def test_real_model_gate_accepts_hashed_media_and_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, _ = _write_evidence(tmp_path)
    _install_runtime_stubs(monkeypatch)

    result = verify._real_model_gate(evidence, required=True)

    assert result.status == "PASS"


@pytest.mark.parametrize(
    ("mutation", "expected_detail"),
    [
        (
            lambda payload: payload["input"].update(sha256="x"),
            "input.sha256 must be a 64-character hexadecimal SHA-256",
        ),
        (lambda payload: payload["input"].update(sha256="0" * 64), "input.sha256 does not match"),
        (
            lambda payload: payload["input"].update(duration_seconds=10.0),
            "input.duration_seconds does not match ffprobe",
        ),
        (
            lambda payload: payload["summary"].update(sha256="0" * 64),
            "summary.sha256 does not match",
        ),
        (
            lambda payload: payload["frame_summary"].update(provider="test-provider"),
            "frame_summary.provider contains forbidden",
        ),
        (
            lambda payload: payload["summary"].update(model="mock-model"),
            "summary.model contains forbidden",
        ),
        (
            lambda payload: (
                payload["asr"].pop("run_id"),
                payload["asr"].pop("request_id", None),
            ),
            "asr.request_id or run_id is required",
        ),
    ],
)
def test_real_model_gate_rejects_unverifiable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    expected_detail: str,
) -> None:
    evidence, payload = _write_evidence(tmp_path)
    mutation(payload)
    _rewrite(evidence, payload)
    _install_runtime_stubs(monkeypatch)

    result = verify._real_model_gate(evidence, required=True)

    assert result.status == "FAIL"
    assert expected_detail in result.detail


def test_real_model_gate_rejects_placeholder_artifact_even_with_matching_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, payload = _write_evidence(tmp_path)
    summary = Path(payload["summary"]["artifact"])
    summary.write_text("placeholder output\n", encoding="utf-8")
    payload["summary"]["sha256"] = _sha256(summary)
    _rewrite(evidence, payload)
    _install_runtime_stubs(monkeypatch)

    result = verify._real_model_gate(evidence, required=True)

    assert result.status == "FAIL"
    assert "mock/placeholder output" in result.detail


def test_tracked_worktree_gate_rejects_tracked_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verify,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=" M scripts/verify.py\n",
            stderr="",
        ),
    )

    result = verify._tracked_worktree_gate()

    assert result.status == "FAIL"
    assert "clean tracked worktree" in result.detail


def test_probe_media_duration_uses_ffprobe_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(verify.shutil, "which", lambda _tool: "ffprobe")
    monkeypatch.setattr(
        verify,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="42.25\n",
            stderr="",
        ),
    )

    assert verify._probe_media_duration(media) == 42.25


def test_release_profile_runs_clean_worktree_gate_first() -> None:
    gates = verify._gates("release", None)

    assert gates[0] is verify._tracked_worktree_gate
