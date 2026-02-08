"""Baseline keyframe service that writes canonical JSONL output."""

from __future__ import annotations

import hashlib
import json
import logging
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
    selected_details: list[dict[str, object]] = field(default_factory=list)


class KeyframeBaselineService:
    """Stable-sampling baseline (no real decoding) for keyframe extraction."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store

    def run(
        self,
        project_id: str,
        *,
        duration_seconds: float,
        interval_seconds: float = 5.0,
        reason: str = "sample",
    ) -> list[KeyframeRecord]:
        """Generate baseline keyframe rows and write ``frames/keyframes.jsonl``."""
        if reason not in ALLOWED_KEYFRAME_REASONS:
            raise ValueError(f"invalid keyframe reason: {reason}")

        self._workspace_store.ensure_project_layout(project_id)
        timestamps = stable_sampling_timestamps(duration_seconds, interval_seconds=interval_seconds)

        records: list[KeyframeRecord] = []
        for index, ts in enumerate(timestamps, start=1):
            frame_id = f"frame_{index:06d}"
            image_name = f"slide_{index:06d}.jpg"
            image_path = self._workspace_store.path(project_id, "frames", "images", image_name)
            key_hash = hashlib.sha1(f"{project_id}|{frame_id}|{ts}".encode()).hexdigest()
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

        self._write_jsonl(self._workspace_store.keyframes_file(project_id), records)
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

    def run_from_features(
        self,
        project_id: str,
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
        self._workspace_store.ensure_project_layout(project_id)
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
            self._write_jsonl(self._workspace_store.keyframes_file(project_id), [])
            diagnostics.timings_ms["write_keyframes_jsonl"] = (perf_counter() - t0) * 1000.0
            t1 = perf_counter()
            self._write_selection_trace(
                self._workspace_store.path(
                    project_id, "frames", "metrics", "selection_trace.jsonl"
                ),
                diagnostics,
            )
            diagnostics.timings_ms["write_selection_trace_jsonl"] = (perf_counter() - t1) * 1000.0
            diagnostics.timings_ms["total"] = (perf_counter() - run_start) * 1000.0
            self._write_timing_report(
                self._workspace_store.path(project_id, "frames", "metrics", "timing_report.json"),
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

                    def fallback_rank(frame: FrameFeature) -> float:
                        if diff_max <= diff_min:
                            stable_score = 1.0
                        else:
                            stable_score = 1.0 - ((frame.diff - diff_min) / (diff_max - diff_min))
                        if sharp_max <= sharp_min:
                            sharp_score = 1.0
                        else:
                            sharp_score = (frame.sharpness - sharp_min) / (sharp_max - sharp_min)
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
            image_path = self._workspace_store.path(project_id, "frames", "images", image_name)
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
        self._write_jsonl(self._workspace_store.keyframes_file(project_id), records)
        diagnostics.timings_ms["write_keyframes_jsonl"] = (
            perf_counter() - t_write_keyframes
        ) * 1000.0

        t_write_metrics = perf_counter()
        self._write_metrics_csv(
            self._workspace_store.path(project_id, "frames", "metrics", "diff_curve.csv"), frames
        )
        diagnostics.timings_ms["write_diff_curve_csv"] = (perf_counter() - t_write_metrics) * 1000.0

        t_write_trace = perf_counter()
        self._write_selection_trace(
            self._workspace_store.path(project_id, "frames", "metrics", "selection_trace.jsonl"),
            diagnostics,
        )
        diagnostics.timings_ms["write_selection_trace_jsonl"] = (
            perf_counter() - t_write_trace
        ) * 1000.0
        diagnostics.timings_ms["total"] = (perf_counter() - run_start) * 1000.0

        self._write_timing_report(
            self._workspace_store.path(project_id, "frames", "metrics", "timing_report.json"),
            diagnostics,
        )

        if logger is not None:
            logger.info(
                "[select] segments=%s stable_candidates=%s fallback_candidates=%s selected=%s total=%.2fms",
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
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
