from __future__ import annotations

import json
from pathlib import Path

from infra import FileSystemWorkspaceStore
from keyframes import FrameFeature, KeyframeAlgorithmService
from keyframes.algorithm import CandidateFrame, detect_stable_segments, select_with_constraints


def _build_frames() -> list[FrameFeature]:
    frames: list[FrameFeature] = []
    for idx in range(60):
        ts = idx * 0.5
        diff = 0.02 if idx % 12 > 2 else 0.16
        sharp = 100 + (idx % 5) * 4
        frames.append(
            FrameFeature(
                ts=ts,
                diff=diff,
                sharpness=sharp,
                hash_hex=f"{(idx // 6):040x}",
                text_density=0.3 + ((idx // 6) % 3) * 0.2,
            )
        )
    return frames


def test_detect_stable_segments_returns_non_empty() -> None:
    segments = detect_stable_segments(_build_frames(), lookback=6, mad_scale=2.0, min_stable_len=3)
    assert segments
    assert all(start <= end for start, end in segments)


def test_algorithm_service_respects_paths_and_reason_set(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeAlgorithmService(store)

    records = service.run_from_features(
        "project-algo",
        frames=_build_frames(),
        min_gap_seconds=2.0,
        fallback_gap_seconds=8.0,
        k_max=25,
    )

    assert records
    assert store.keyframes_file("project-algo").exists()
    assert store.path("project-algo", "frames", "metrics", "diff_curve.csv").exists()
    assert store.path("project-algo", "frames", "metrics", "selection_trace.jsonl").exists()
    timing_path = store.path("project-algo", "frames", "metrics", "timing_report.json")
    assert timing_path.exists()
    assert all(record.reason in {"stable", "scene", "cluster", "sample"} for record in records)
    assert all(
        record.path.startswith(str(store.path("project-algo", "frames", "images")))
        for record in records
    )
    diagnostics = service.last_run_diagnostics
    assert diagnostics.frame_count == len(_build_frames())
    assert diagnostics.selected_count == len(records)
    assert diagnostics.timings_ms["total"] > 0.0
    timing_payload = json.loads(timing_path.read_text(encoding="utf-8"))
    assert timing_payload["timings_ms"]["total"] > 0.0


def test_select_with_constraints_enforces_hash_dedup() -> None:
    candidates = [
        CandidateFrame(
            ts=0.0,
            hash_hex="a" * 40,
            sharpness=100.0,
            stability=0.9,
            text_density=0.5,
            reason="stable",
        ),
        CandidateFrame(
            ts=3.0,
            hash_hex="a" * 40,
            sharpness=99.0,
            stability=0.8,
            text_density=0.4,
            reason="stable",
        ),
        CandidateFrame(
            ts=6.0,
            hash_hex="f" * 40,
            sharpness=110.0,
            stability=0.8,
            text_density=0.4,
            reason="stable",
        ),
    ]
    selected = select_with_constraints(
        candidates,
        base_scores={0.0: 0.9, 3.0: 0.85, 6.0: 0.8},
        min_gap_seconds=1.0,
        fallback_gap_seconds=10.0,
        duration_seconds=7.0,
        min_hash_dist=1,
        k_max=3,
    )

    assert len(selected) == 2
    assert [item.ts for item in selected] == [0.0, 6.0]


def test_algorithm_service_bucket_fallback_emits_sample_reason(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeAlgorithmService(store)
    frames = [
        FrameFeature(
            ts=float(idx),
            diff=0.2,
            sharpness=40.0 + idx,
            hash_hex=f"{idx:040x}",
            text_density=0.2,
        )
        for idx in range(30)
    ]

    records = service.run_from_features(
        "project-fallback",
        frames=frames,
        stable_mad_scale=0.0,
        min_stable_len=50,
        fallback_gap_seconds=10.0,
        min_gap_seconds=2.0,
    )

    assert records
    assert any(record.reason == "sample" for record in records)
