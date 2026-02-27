"""Demo: algorithmic keyframe selection from synthetic or CSV features.

Usage examples:

  python scripts/demo_keyframes_algorithm.py --project-id p_demo_algo
  python scripts/demo_keyframes_algorithm.py --features-csv data/frame_features.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import secrets
from pathlib import Path

from frame_summary import FrameSummaryService, QwenFrameSummaryProvider
from infra import FileSystemWorkspaceStore
from keyframes import FrameFeature, KeyframeAlgorithmService


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _synthetic_features(duration_seconds: float, fps: float, seed: int) -> list[FrameFeature]:
    if fps <= 0:
        raise ValueError("fps must be > 0")
    rng = random.Random(seed)
    count = int(duration_seconds * fps)
    features: list[FrameFeature] = []
    for idx in range(count):
        ts = round(idx / fps, 3)
        region = (idx // max(int(fps * 8), 1)) % 4
        slide_id = f"slide_{region}_{(idx // max(int(fps * 30), 1))}"

        if (idx % max(int(fps * 12), 1)) < int(fps * 2):
            diff = 0.12 + rng.uniform(0.05, 0.16)
            sharpness = 70 + rng.uniform(-10, 30)
        else:
            diff = 0.02 + rng.uniform(0.0, 0.03)
            sharpness = 110 + rng.uniform(-20, 50)

        text_density = 0.35 + (0.1 * region) + rng.uniform(-0.05, 0.08)
        hash_hex = hashlib.sha1(f"{slide_id}|{idx // max(int(fps * 2), 1)}".encode()).hexdigest()
        features.append(
            FrameFeature(
                ts=ts,
                diff=max(0.0, diff),
                sharpness=max(1.0, sharpness),
                hash_hex=hash_hex,
                text_density=max(0.0, min(text_density, 1.0)),
            )
        )
    return features


def _load_features_csv(path: Path) -> list[FrameFeature]:
    rows: list[FrameFeature] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for line in reader:
            rows.append(
                FrameFeature(
                    ts=float(line["ts"]),
                    diff=float(line["diff"]),
                    sharpness=float(line["sharpness"]),
                    hash_hex=line["hash_hex"],
                    text_density=float(line.get("text_density", "0") or 0),
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo algorithmic keyframe selection")
    parser.add_argument("--workspace-root", default="workspaces", help="Workspace root directory")
    parser.add_argument("--project-id", default=None, help="Optional fixed project id")
    parser.add_argument("--job-id", default=None, help="Optional fixed job id")
    parser.add_argument("--duration", type=float, default=180.0, help="Synthetic duration seconds")
    parser.add_argument("--fps", type=float, default=3.0, help="Synthetic sampling fps")
    parser.add_argument("--seed", type=int, default=7, help="Synthetic random seed")
    parser.add_argument(
        "--features-csv", default=None, help="Optional CSV path with frame features"
    )
    parser.add_argument("--min-gap", type=float, default=2.0, help="Hard minimum gap in seconds")
    parser.add_argument(
        "--fallback-gap", type=float, default=12.0, help="Coverage bucket size in seconds"
    )
    parser.add_argument("--k-max", type=int, default=120, help="Max selected keyframes")
    args = parser.parse_args()

    project_id = args.project_id or _gen_id("p_demo")
    job_id = args.job_id or _gen_id("j_demo")
    workspace = FileSystemWorkspaceStore(Path(args.workspace_root))
    workspace.ensure_job_layout(project_id, job_id)
    service = KeyframeAlgorithmService(workspace)

    if args.features_csv:
        frames = _load_features_csv(Path(args.features_csv))
        source_label = f"csv={args.features_csv}"
    else:
        frames = _synthetic_features(args.duration, args.fps, args.seed)
        source_label = f"synthetic duration={args.duration}s fps={args.fps} seed={args.seed}"

    records = service.run_from_features(
        project_id,
        job_id,
        frames=frames,
        min_gap_seconds=args.min_gap,
        fallback_gap_seconds=args.fallback_gap,
        k_max=args.k_max,
    )
    frame_summary_service = FrameSummaryService(workspace, QwenFrameSummaryProvider())
    frame_summary_rows = frame_summary_service.run(project_id, job_id, language_hint="zh")

    print("[demo] keyframe algorithm run complete")
    print(f"[demo] source: {source_label}")
    print(f"[demo] project_id: {project_id}")
    print(f"[demo] job_id: {job_id}")
    print(f"[demo] frames_in: {len(frames)}")
    print(f"[demo] keyframes_out: {len(records)}")
    print(f"[demo] frame_summary_rows_out: {len(frame_summary_rows)}")
    print(f"[demo] keyframes_jsonl: {workspace.keyframes_file(project_id, job_id)}")
    metrics_path = workspace.job_path(project_id, job_id, "frames", "metrics", "diff_curve.csv")
    print(f"[demo] metrics_csv: {metrics_path}")
    print(f"[demo] frame_summary_jsonl: {workspace.frame_summary_file(project_id, job_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
