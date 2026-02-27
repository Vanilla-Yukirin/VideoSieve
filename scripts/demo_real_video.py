"""Demo: real-video keyframe extraction + frame summary.

Usage:
  conda activate VideoSieve
  python scripts/demo_real_video.py --video "D:/path/to/source.mp4"
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
from pathlib import Path
from time import perf_counter

from frame_summary import FrameSummaryService, QwenFrameSummaryProvider
from infra import FileSystemWorkspaceStore
from keyframes import KeyframeAlgorithmService, extract_video_features, write_images_for_records


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _configure_logger(log_path: Path, level: str) -> logging.Logger:
    """Create one logger that writes to both terminal and file."""
    logger = logging.getLogger("videosieve.demo_real_video")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def main() -> int:
    parser = argparse.ArgumentParser(description="Real video keyframe + frame summary demo")
    parser.add_argument("--video", required=True, help="Path to source video")
    parser.add_argument("--workspace-root", default="workspaces", help="Workspace root directory")
    parser.add_argument("--project-id", default=None, help="Optional fixed project id")
    parser.add_argument("--job-id", default=None, help="Optional fixed job id")
    parser.add_argument("--sample-fps", type=float, default=3.0, help="Feature extraction fps")
    parser.add_argument("--min-gap", type=float, default=2.0, help="Hard minimum time gap")
    parser.add_argument("--fallback-gap", type=float, default=12.0, help="Coverage fallback bucket")
    parser.add_argument("--min-hash-dist", type=int, default=8, help="Min hamming distance dedup")
    parser.add_argument("--stable-lookback", type=int, default=12, help="Stable threshold lookback")
    parser.add_argument("--stable-mad-scale", type=float, default=3.0, help="Stable MAD scale")
    parser.add_argument("--min-stable-len", type=int, default=4, help="Min stable run length")
    parser.add_argument("--k-max", type=int, default=200, help="Max keyframe count")
    parser.add_argument(
        "--extract-progress-every",
        type=int,
        default=150,
        help="Progress log interval during feature extraction",
    )
    parser.add_argument(
        "--verbose-selected",
        type=int,
        default=20,
        help="Print top N selected frame details",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level: INFO/DEBUG")
    args = parser.parse_args()

    source = Path(args.video)
    if not source.exists():
        raise ValueError(f"video not found: {source}")

    project_id = args.project_id or _gen_id("p_real")
    job_id = args.job_id or _gen_id("j_real")
    workspace = FileSystemWorkspaceStore(Path(args.workspace_root))
    workspace.ensure_job_layout(project_id, job_id)
    log_path = workspace.job_path(project_id, job_id, "logs", "demo_real_video.log")
    logger = _configure_logger(log_path, args.log_level)

    logger.info("[demo] project_id=%s", project_id)
    logger.info("[demo] job_id=%s", job_id)
    logger.info("[demo] video=%s", source)
    logger.info(
        "[demo] params sample_fps=%s min_gap=%s fallback_gap=%s "
        "min_hash_dist=%s stable_lookback=%s stable_mad_scale=%s "
        "min_stable_len=%s k_max=%s",
        args.sample_fps,
        args.min_gap,
        args.fallback_gap,
        args.min_hash_dist,
        args.stable_lookback,
        args.stable_mad_scale,
        args.min_stable_len,
        args.k_max,
    )

    logger.info("[demo] extracting frame features...")
    t_extract = perf_counter()
    frames = extract_video_features(
        source,
        sample_fps=args.sample_fps,
        logger=logger,
        progress_every_samples=args.extract_progress_every,
    )
    extract_elapsed = perf_counter() - t_extract
    logger.info(
        "[demo] extraction_done frame_features=%s elapsed=%.2fs", len(frames), extract_elapsed
    )

    logger.info("[demo] selecting keyframes...")
    t_select = perf_counter()
    keyframe_service = KeyframeAlgorithmService(workspace)
    records = keyframe_service.run_from_features(
        project_id,
        job_id,
        frames=frames,
        min_gap_seconds=args.min_gap,
        fallback_gap_seconds=args.fallback_gap,
        min_hash_dist=args.min_hash_dist,
        stable_lookback=args.stable_lookback,
        stable_mad_scale=args.stable_mad_scale,
        min_stable_len=args.min_stable_len,
        k_max=args.k_max,
        logger=logger,
    )
    select_elapsed = perf_counter() - t_select
    diagnostics = keyframe_service.last_run_diagnostics
    logger.info("[demo] selection_done keyframes=%s elapsed=%.2fs", len(records), select_elapsed)

    logger.info("[demo] writing keyframe images...")
    t_write_images = perf_counter()
    write_images_for_records(
        source,
        timestamps_to_paths=[(record.ts, Path(record.path)) for record in records],
    )
    images_elapsed = perf_counter() - t_write_images
    logger.info("[demo] image_write_done elapsed=%.2fs", images_elapsed)

    logger.info("[demo] running frame summary provider...")
    t_frame_summary = perf_counter()
    frame_summary_service = FrameSummaryService(workspace, QwenFrameSummaryProvider())
    frame_summary_rows = frame_summary_service.run(project_id, job_id, language_hint="zh")
    frame_summary_elapsed = perf_counter() - t_frame_summary
    logger.info(
        "[demo] frame_summary_done rows=%s elapsed=%.2fs",
        len(frame_summary_rows),
        frame_summary_elapsed,
    )

    logger.info("[demo] completed")
    logger.info("[demo] frame_features: %s", len(frames))
    logger.info("[demo] keyframes_out: %s", len(records))
    logger.info("[demo] stable_segments: %s", diagnostics.stable_segment_count)
    logger.info("[demo] stable_candidates: %s", diagnostics.stable_candidate_count)
    logger.info("[demo] fallback_candidates: %s", diagnostics.fallback_candidate_count)
    logger.info("[demo] frame_summary_rows_out: %s", len(frame_summary_rows))
    logger.info("[demo] keyframes_jsonl: %s", workspace.keyframes_file(project_id, job_id))
    logger.info(
        "[demo] keyframes_images_dir: %s",
        workspace.job_path(project_id, job_id, "frames", "images"),
    )
    logger.info(
        "[demo] metrics_csv: %s",
        workspace.job_path(project_id, job_id, "frames", "metrics", "diff_curve.csv"),
    )
    trace_path = workspace.job_path(
        project_id, job_id, "frames", "metrics", "selection_trace.jsonl"
    )
    timing_path = workspace.job_path(project_id, job_id, "frames", "metrics", "timing_report.json")
    logger.info("[demo] selection_trace_jsonl: %s", trace_path)
    logger.info("[demo] timing_report_json: %s", timing_path)
    logger.info("[demo] frame_summary_jsonl: %s", workspace.frame_summary_file(project_id, job_id))
    logger.info("[demo] log_file: %s", log_path)

    if diagnostics.selected_details:
        logger.info("[demo] selected frame details")
        for item in diagnostics.selected_details[: max(args.verbose_selected, 0)]:
            logger.info(
                "  - %s",
                json.dumps(
                    {
                        "rank": item["rank"],
                        "ts": item["ts"],
                        "reason": item["reason"],
                        "score": item["score"],
                    },
                    ensure_ascii=False,
                ),
            )

    logger.info(
        "[demo] stage_elapsed_seconds extract=%.2f select=%.2f "
        "write_images=%.2f frame_summary=%.2f",
        extract_elapsed,
        select_elapsed,
        images_elapsed,
        frame_summary_elapsed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
