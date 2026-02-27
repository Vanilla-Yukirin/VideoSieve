"""Baseline keyframe service that writes canonical JSONL output."""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from infra.interfaces import WorkspaceStore

from .algorithm import (
    CandidateFrame,
    FrameFeature,
    build_stable_candidates,
    detect_stable_segments,
    score_candidates,
    select_with_constraints,
)
from .extractor import extract_video_features, write_images_for_records
from .models import ALLOWED_KEYFRAME_REASONS, KeyframeRecord
from .sampler import stable_sampling_timestamps


@dataclass
class KeyframeRunDiagnostics:
    """Debug info produced by one algorithmic keyframe run."""

    frame_count: int = 0
    stable_segment_count: int = 0
    stable_candidate_count: int = 0
    fallback_candidate_count: int = 0
    selected_count: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, object] = field(default_factory=dict)
    source_mode: str = "algorithm"
    analysis_video_path: str | None = None
    quality_video_path: str | None = None
    same_source_resolved: bool | None = None
    selected_details: list[dict[str, object]] = field(default_factory=list)


class KeyframeBaselineService:
    """Stable-sampling baseline (no real decoding) for keyframe extraction."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store

    def run(
        self,
        project_id: str,
        job_id: str,
        *,
        duration_seconds: float,
        interval_seconds: float = 5.0,
        reason: str = "sample",
    ) -> list[KeyframeRecord]:
        """Generate baseline keyframe rows and write ``frames/keyframes.jsonl``."""
        if reason not in ALLOWED_KEYFRAME_REASONS:
            raise ValueError(f"invalid keyframe reason: {reason}")

        self._workspace_store.ensure_job_layout(project_id, job_id)
        timestamps = stable_sampling_timestamps(duration_seconds, interval_seconds=interval_seconds)

        records: list[KeyframeRecord] = []
        for index, ts in enumerate(timestamps, start=1):
            frame_id = f"frame_{index:06d}"
            image_name = f"slide_{index:06d}.jpg"
            image_path = self._workspace_store.job_path(
                project_id, job_id, "frames", "images", image_name
            )
            key_hash = hashlib.sha1(f"{project_id}|{job_id}|{frame_id}|{ts}".encode()).hexdigest()
            records.append(
                KeyframeRecord(
                    frame_id=frame_id,
                    ts=ts,
                    path=str(image_path),
                    hash=key_hash,
                    score=1.0,
                    reason=reason,
                )
            )

        self._write_jsonl(self._workspace_store.keyframes_file(project_id, job_id), records)
        return records

    @staticmethod
    def _write_jsonl(path: Path, records: list[KeyframeRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")


class KeyframeAlgorithmService:
    """Algorithmic keyframe service from precomputed frame features."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store
        self.last_run_diagnostics = KeyframeRunDiagnostics()

    def run_from_dual_sources(
        self,
        project_id: str,
        job_id: str,
        *,
        analysis_video_path: str | Path,
        quality_video_path: str | Path,
        same_source: bool | None = None,
        sample_fps: float = 3.0,
        resize_width: int = 320,
        extract_progress_every: int = 150,
        min_gap_seconds: float = 2.0,
        fallback_gap_seconds: float = 12.0,
        min_hash_dist: int = 8,
        stable_lookback: int = 12,
        stable_mad_scale: float = 3.0,
        min_stable_len: int = 4,
        k_max: int | None = None,
        logger: logging.Logger | None = None,
    ) -> list[KeyframeRecord]:
        """Run dual-source keyframe flow with single-source smart reuse.

        The method keeps output contracts unchanged:
        - frames/keyframes.jsonl
        - frames/images/*.jpg
        - frames/metrics/*
        """
        analysis_path = Path(analysis_video_path)
        quality_path = Path(quality_video_path)

        # Same-source rule: explicit parameter wins; otherwise infer from resolved paths.
        if same_source is None:
            same_source_resolved = analysis_path.resolve() == quality_path.resolve()
        else:
            same_source_resolved = same_source

        dual_start = perf_counter()

        # Stage 1: fast analysis asset for feature extraction and timestamp selection.
        t_extract = perf_counter()
        analysis_frames = extract_video_features(
            analysis_path,
            sample_fps=sample_fps,
            resize_width=resize_width,
            logger=logger,
            progress_every_samples=extract_progress_every,
        )
        extract_ms = (perf_counter() - t_extract) * 1000.0

        records = self.run_from_features(
            project_id,
            job_id,
            frames=analysis_frames,
            min_gap_seconds=min_gap_seconds,
            fallback_gap_seconds=fallback_gap_seconds,
            min_hash_dist=min_hash_dist,
            stable_lookback=stable_lookback,
            stable_mad_scale=stable_mad_scale,
            min_stable_len=min_stable_len,
            k_max=k_max,
            logger=logger,
        )

        # Stage 2: final frame writing uses quality asset unless single-source reuse applies.
        write_source = analysis_path if same_source_resolved else quality_path
        t_write = perf_counter()
        write_images_for_records(
            write_source,
            timestamps_to_paths=[(record.ts, Path(record.path)) for record in records],
        )
        write_ms = (perf_counter() - t_write) * 1000.0

        diagnostics = self.last_run_diagnostics
        diagnostics.source_mode = "single_source" if same_source_resolved else "dual_source"
        diagnostics.analysis_video_path = str(analysis_path)
        diagnostics.quality_video_path = str(quality_path)
        diagnostics.same_source_resolved = same_source_resolved
        diagnostics.timings_ms["extract_analysis"] = extract_ms
        diagnostics.timings_ms["write_images_final"] = write_ms
        diagnostics.timings_ms["total_pipeline"] = (perf_counter() - dual_start) * 1000.0
        diagnostics.parameters["sample_fps"] = sample_fps
        diagnostics.parameters["resize_width"] = resize_width
        diagnostics.parameters["extract_progress_every"] = extract_progress_every

        # Persist updated diagnostics after image-writing stage so metrics
        # include dual-source timings.
        self._write_selection_trace(
            self._workspace_store.job_path(
                project_id, job_id, "frames", "metrics", "selection_trace.jsonl"
            ),
            diagnostics,
        )
        self._write_timing_report(
            self._workspace_store.job_path(
                project_id, job_id, "frames", "metrics", "timing_report.json"
            ),
            diagnostics,
        )

        if logger is not None:
            logger.info(
                "[dual-source] mode=%s extract_analysis=%.2fms write_images=%.2fms "
                "total=%.2fms selected=%s",
                diagnostics.source_mode,
                diagnostics.timings_ms.get("extract_analysis", 0.0),
                diagnostics.timings_ms.get("write_images_final", 0.0),
                diagnostics.timings_ms.get("total_pipeline", 0.0),
                diagnostics.selected_count,
            )

        return records

    def run_from_features(
        self,
        project_id: str,
        job_id: str,
        *,
        frames: list[FrameFeature],
        min_gap_seconds: float = 2.0,
        fallback_gap_seconds: float = 12.0,
        min_hash_dist: int = 8,
        stable_lookback: int = 12,
        stable_mad_scale: float = 3.0,
        min_stable_len: int = 4,
        k_max: int | None = None,
        logger: logging.Logger | None = None,
    ) -> list[KeyframeRecord]:
        """Run stable detection + scoring + constrained selection."""
        self._workspace_store.ensure_job_layout(project_id, job_id)
        diagnostics = KeyframeRunDiagnostics(
            frame_count=len(frames),
            parameters={
                "min_gap_seconds": min_gap_seconds,
                "fallback_gap_seconds": fallback_gap_seconds,
                "min_hash_dist": min_hash_dist,
                "stable_lookback": stable_lookback,
                "stable_mad_scale": stable_mad_scale,
                "min_stable_len": min_stable_len,
                "k_max": k_max,
            },
        )
        self.last_run_diagnostics = diagnostics
        run_start = perf_counter()
        if not frames:
            t0 = perf_counter()
            self._write_jsonl(self._workspace_store.keyframes_file(project_id, job_id), [])
            diagnostics.timings_ms["write_keyframes_jsonl"] = (perf_counter() - t0) * 1000.0
            t1 = perf_counter()
            self._write_selection_trace(
                self._workspace_store.job_path(
                    project_id, job_id, "frames", "metrics", "selection_trace.jsonl"
                ),
                diagnostics,
            )
            diagnostics.timings_ms["write_selection_trace_jsonl"] = (perf_counter() - t1) * 1000.0
            diagnostics.timings_ms["total"] = (perf_counter() - run_start) * 1000.0
            self._write_timing_report(
                self._workspace_store.job_path(
                    project_id, job_id, "frames", "metrics", "timing_report.json"
                ),
                diagnostics,
            )
            return []

        duration_seconds = max(frame.ts for frame in frames) + 0.001
        t_stable = perf_counter()
        segments = detect_stable_segments(
            frames,
            lookback=stable_lookback,
            mad_scale=stable_mad_scale,
            min_stable_len=min_stable_len,
        )
        diagnostics.timings_ms["stable_detection"] = (perf_counter() - t_stable) * 1000.0
        diagnostics.stable_segment_count = len(segments)

        t_candidates = perf_counter()
        candidates = build_stable_candidates(frames, segments)
        diagnostics.timings_ms["build_stable_candidates"] = (perf_counter() - t_candidates) * 1000.0
        diagnostics.stable_candidate_count = len(candidates)

        # Coverage fallback per time bucket:
        # if one bucket has no stable candidate, add one sample candidate from raw frames.
        t_fallback = perf_counter()
        bucket_start = 0.0
        while bucket_start < duration_seconds:
            bucket_end = bucket_start + fallback_gap_seconds
            has_stable = any(
                bucket_start <= candidate.ts < bucket_end and candidate.reason == "stable"
                for candidate in candidates
            )
            if not has_stable:
                bucket_frames = [frame for frame in frames if bucket_start <= frame.ts < bucket_end]
                if bucket_frames:
                    frame_diffs = [frame.diff for frame in bucket_frames]
                    frame_sharp = [frame.sharpness for frame in bucket_frames]
                    diff_min = min(frame_diffs)
                    diff_max = max(frame_diffs)
                    sharp_min = min(frame_sharp)
                    sharp_max = max(frame_sharp)

                    def fallback_rank(
                        frame: FrameFeature,
                        *,
                        _diff_min: float = diff_min,
                        _diff_max: float = diff_max,
                        _sharp_min: float = sharp_min,
                        _sharp_max: float = sharp_max,
                    ) -> float:
                        if _diff_max <= _diff_min:
                            stable_score = 1.0
                        else:
                            stable_score = 1.0 - (
                                (frame.diff - _diff_min) / (_diff_max - _diff_min)
                            )
                        if _sharp_max <= _sharp_min:
                            sharp_score = 1.0
                        else:
                            sharp_score = (frame.sharpness - _sharp_min) / (_sharp_max - _sharp_min)
                        return (0.65 * stable_score) + (0.35 * sharp_score)

                    chosen = max(bucket_frames, key=fallback_rank)
                    candidates.append(
                        CandidateFrame(
                            ts=chosen.ts,
                            hash_hex=chosen.hash_hex,
                            sharpness=chosen.sharpness,
                            stability=0.5,
                            text_density=chosen.text_density,
                            reason="sample",
                        )
                    )
                    diagnostics.fallback_candidate_count += 1
            bucket_start = bucket_end
        diagnostics.timings_ms["fallback_bucket_fill"] = (perf_counter() - t_fallback) * 1000.0

        if not candidates:
            for ts in stable_sampling_timestamps(
                duration_seconds, interval_seconds=fallback_gap_seconds
            ):
                nearest = min(frames, key=lambda frame: abs(frame.ts - ts))
                candidates.append(
                    CandidateFrame(
                        ts=nearest.ts,
                        hash_hex=nearest.hash_hex,
                        sharpness=nearest.sharpness,
                        stability=0.5,
                        text_density=nearest.text_density,
                        reason="sample",
                    )
                )

        t_score = perf_counter()
        scored_candidates = [
            item
            if item.reason in ALLOWED_KEYFRAME_REASONS
            else CandidateFrame(
                ts=item.ts,
                hash_hex=item.hash_hex,
                sharpness=item.sharpness,
                stability=item.stability,
                text_density=item.text_density,
                reason="sample",
            )
            for item in candidates
        ]
        base_scores = score_candidates(scored_candidates)
        diagnostics.timings_ms["score_candidates"] = (perf_counter() - t_score) * 1000.0

        t_select = perf_counter()
        selected = select_with_constraints(
            scored_candidates,
            base_scores=base_scores,
            min_gap_seconds=min_gap_seconds,
            fallback_gap_seconds=fallback_gap_seconds,
            duration_seconds=duration_seconds,
            min_hash_dist=min_hash_dist,
            k_max=k_max,
        )
        diagnostics.timings_ms["select_with_constraints"] = (perf_counter() - t_select) * 1000.0

        records: list[KeyframeRecord] = []
        for index, candidate in enumerate(selected, start=1):
            frame_id = f"frame_{index:06d}"
            image_name = f"slide_{index:06d}.jpg"
            image_path = self._workspace_store.job_path(
                project_id, job_id, "frames", "images", image_name
            )
            records.append(
                KeyframeRecord(
                    frame_id=frame_id,
                    ts=round(candidate.ts, 3),
                    path=str(image_path),
                    hash=candidate.hash_hex,
                    score=round(base_scores.get(candidate.ts, 0.5), 4),
                    reason=candidate.reason,
                )
            )

        diagnostics.selected_count = len(records)
        diagnostics.selected_details = [
            {
                "rank": index,
                "ts": round(candidate.ts, 3),
                "reason": candidate.reason,
                "score": round(base_scores.get(candidate.ts, 0.5), 4),
                "hash": candidate.hash_hex,
            }
            for index, candidate in enumerate(selected, start=1)
        ]

        t_write_keyframes = perf_counter()
        self._write_jsonl(self._workspace_store.keyframes_file(project_id, job_id), records)
        diagnostics.timings_ms["write_keyframes_jsonl"] = (
            perf_counter() - t_write_keyframes
        ) * 1000.0

        t_write_metrics = perf_counter()
        self._write_metrics_csv(
            self._workspace_store.job_path(
                project_id, job_id, "frames", "metrics", "diff_curve.csv"
            ),
            frames,
        )
        diagnostics.timings_ms["write_diff_curve_csv"] = (perf_counter() - t_write_metrics) * 1000.0

        t_write_trace = perf_counter()
        self._write_selection_trace(
            self._workspace_store.job_path(
                project_id, job_id, "frames", "metrics", "selection_trace.jsonl"
            ),
            diagnostics,
        )
        diagnostics.timings_ms["write_selection_trace_jsonl"] = (
            perf_counter() - t_write_trace
        ) * 1000.0
        diagnostics.timings_ms["total"] = (perf_counter() - run_start) * 1000.0

        self._write_timing_report(
            self._workspace_store.job_path(
                project_id, job_id, "frames", "metrics", "timing_report.json"
            ),
            diagnostics,
        )

        if logger is not None:
            logger.info(
                "[select] segments=%s stable_candidates=%s fallback_candidates=%s "
                "selected=%s total=%.2fms",
                diagnostics.stable_segment_count,
                diagnostics.stable_candidate_count,
                diagnostics.fallback_candidate_count,
                diagnostics.selected_count,
                diagnostics.timings_ms.get("total", 0.0),
            )

        return records

    @staticmethod
    def _write_metrics_csv(path: Path, frames: list[FrameFeature]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write("ts,diff,sharpness,text_density\n")
            for frame in frames:
                handle.write(
                    f"{frame.ts:.3f},{frame.diff:.6f},{frame.sharpness:.6f},{frame.text_density:.6f}\n"
                )

    @staticmethod
    def _write_jsonl(path: Path, records: list[KeyframeRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")

    @staticmethod
    def _write_selection_trace(path: Path, diagnostics: KeyframeRunDiagnostics) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            summary = {
                "kind": "summary",
                "frame_count": diagnostics.frame_count,
                "stable_segment_count": diagnostics.stable_segment_count,
                "stable_candidate_count": diagnostics.stable_candidate_count,
                "fallback_candidate_count": diagnostics.fallback_candidate_count,
                "selected_count": diagnostics.selected_count,
                "timings_ms": {
                    name: round(value, 3) for name, value in diagnostics.timings_ms.items()
                },
                "source_mode": diagnostics.source_mode,
                "analysis_video_path": diagnostics.analysis_video_path,
                "quality_video_path": diagnostics.quality_video_path,
                "same_source_resolved": diagnostics.same_source_resolved,
            }
            handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
            for detail in diagnostics.selected_details:
                event = {"kind": "selected", **detail}
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_timing_report(path: Path, diagnostics: KeyframeRunDiagnostics) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "frame_count": diagnostics.frame_count,
            "stable_segment_count": diagnostics.stable_segment_count,
            "stable_candidate_count": diagnostics.stable_candidate_count,
            "fallback_candidate_count": diagnostics.fallback_candidate_count,
            "selected_count": diagnostics.selected_count,
            "parameters": diagnostics.parameters,
            "timings_ms": {name: round(value, 3) for name, value in diagnostics.timings_ms.items()},
            "source_mode": diagnostics.source_mode,
            "analysis_video_path": diagnostics.analysis_video_path,
            "quality_video_path": diagnostics.quality_video_path,
            "same_source_resolved": diagnostics.same_source_resolved,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_images_zip(workspace_store: WorkspaceStore, project_id: str, job_id: str) -> Path:
    """Create ``frames/images.zip`` from ``frames/images/*.jpg|*.jpeg``."""

    images_dir = workspace_store.job_path(project_id, job_id, "frames", "images")
    if not images_dir.exists() or not images_dir.is_dir():
        raise FileNotFoundError(f"keyframe images directory not found: {images_dir}")

    image_files = sorted(
        [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        ],
        key=lambda item: item.name,
    )
    if not image_files:
        raise FileNotFoundError(f"keyframe images not found: {images_dir}")

    zip_path = workspace_store.job_path(project_id, job_id, "frames", "images.zip")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for image_path in image_files:
            archive.write(image_path, arcname=image_path.name)
    return zip_path
