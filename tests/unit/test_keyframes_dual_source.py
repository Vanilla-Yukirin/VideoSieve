from __future__ import annotations

import json
from pathlib import Path

from infra import FileSystemWorkspaceStore
from keyframes import FrameFeature, KeyframeAlgorithmService


def _deterministic_frames() -> list[FrameFeature]:
    frames: list[FrameFeature] = []
    for idx in range(90):
        frames.append(
            FrameFeature(
                ts=idx * 0.5,
                diff=0.02 if idx % 10 > 2 else 0.14,
                sharpness=80.0 + (idx % 6) * 3,
                hash_hex=f"{(idx // 4):040x}",
                text_density=0.2 + ((idx // 10) % 4) * 0.1,
            )
        )
    return frames


def test_dual_source_same_source_autodetect_reuses_single_write_source(
    tmp_path: Path, monkeypatch
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeAlgorithmService(store)

    extract_calls: list[Path] = []
    write_calls: list[Path] = []

    def fake_extract(video_path: str | Path, **_kwargs: object) -> list[FrameFeature]:
        extract_calls.append(Path(video_path))
        return _deterministic_frames()

    def fake_write(video_path: str | Path, **_kwargs: object) -> None:
        write_calls.append(Path(video_path))

    monkeypatch.setattr("keyframes.service.extract_video_features", fake_extract)
    monkeypatch.setattr("keyframes.service.write_images_for_records", fake_write)

    source = tmp_path / "asset.mp4"
    records = service.run_from_dual_sources(
        "project-dual-1",
        analysis_video_path=source,
        quality_video_path=source,
    )

    assert records
    assert len(extract_calls) == 1
    assert len(write_calls) == 1
    assert write_calls[0].resolve() == source.resolve()
    assert service.last_run_diagnostics.same_source_resolved is True
    assert service.last_run_diagnostics.source_mode == "single_source"


def test_dual_source_explicit_same_source_overrides_path_inference(
    tmp_path: Path, monkeypatch
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeAlgorithmService(store)

    write_calls: list[Path] = []

    monkeypatch.setattr(
        "keyframes.service.extract_video_features",
        lambda _video_path, **_kwargs: _deterministic_frames(),
    )
    monkeypatch.setattr(
        "keyframes.service.write_images_for_records",
        lambda video_path, **_kwargs: write_calls.append(Path(video_path)),
    )

    analysis = tmp_path / "analysis.mp4"
    quality = tmp_path / "quality.mp4"

    service.run_from_dual_sources(
        "project-dual-2",
        analysis_video_path=analysis,
        quality_video_path=quality,
        same_source=True,
    )
    assert write_calls[-1].resolve() == analysis.resolve()

    service.run_from_dual_sources(
        "project-dual-3",
        analysis_video_path=analysis,
        quality_video_path=quality,
        same_source=False,
    )
    assert write_calls[-1].resolve() == quality.resolve()


def test_dual_source_keeps_keyframe_count_stable_and_writes_additive_timing_fields(
    tmp_path: Path, monkeypatch
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = KeyframeAlgorithmService(store)

    monkeypatch.setattr(
        "keyframes.service.extract_video_features",
        lambda _video_path, **_kwargs: _deterministic_frames(),
    )
    monkeypatch.setattr(
        "keyframes.service.write_images_for_records", lambda *_args, **_kwargs: None
    )

    single = service.run_from_dual_sources(
        "project-single",
        analysis_video_path=tmp_path / "single.mp4",
        quality_video_path=tmp_path / "single.mp4",
    )
    dual = service.run_from_dual_sources(
        "project-dual",
        analysis_video_path=tmp_path / "analysis.mp4",
        quality_video_path=tmp_path / "quality.mp4",
        same_source=False,
    )

    # Different assets should keep selected count stable because timestamps
    # are chosen on analysis asset.
    assert abs(len(single) - len(dual)) <= 1

    timing_path = store.path("project-dual", "frames", "metrics", "timing_report.json")
    payload = json.loads(timing_path.read_text(encoding="utf-8"))

    # Original timing/report fields must remain and new dual-source fields are additive only.
    assert "timings_ms" in payload
    assert "total" in payload["timings_ms"]
    assert "extract_analysis" in payload["timings_ms"]
    assert "write_images_final" in payload["timings_ms"]
    assert "total_pipeline" in payload["timings_ms"]
    assert payload["source_mode"] == "dual_source"
    assert payload["same_source_resolved"] is False
    assert store.keyframes_file("project-dual").exists()
