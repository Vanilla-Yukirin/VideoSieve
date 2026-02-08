"""Video feature extraction helpers for keyframe algorithms."""

from __future__ import annotations

import logging
from time import perf_counter
from pathlib import Path

from .algorithm import FrameFeature


def _require_cv2():
    try:
        import cv2  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "opencv-python is required for real video extraction. "
            "Install it in your environment, then retry."
        ) from exc
    return cv2


def _dhash_hex(gray: object, *, hash_size: int = 8) -> str:
    cv2 = _require_cv2()

    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if flag else "0" for flag in diff.flatten())
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def extract_video_features(
    video_path: str | Path,
    *,
    sample_fps: float = 3.0,
    resize_width: int = 320,
    logger: logging.Logger | None = None,
    progress_every_samples: int = 150,
) -> list[FrameFeature]:
    """Extract per-frame features for keyframe selection from a video file."""
    if sample_fps <= 0:
        raise ValueError("sample_fps must be > 0")
    if resize_width < 64:
        raise ValueError("resize_width must be >= 64")
    if progress_every_samples <= 0:
        raise ValueError("progress_every_samples must be > 0")

    cv2 = _require_cv2()

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"unable to open video: {video_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    if source_fps <= 0:
        source_fps = sample_fps
    step_frames = max(int(round(source_fps / sample_fps)), 1)

    prev_gray: object | None = None
    features: list[FrameFeature] = []
    frame_index = 0
    sampled_count = 0
    start_time = perf_counter()

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % step_frames != 0:
                frame_index += 1
                continue

            ts = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            h, w = frame.shape[:2]
            new_h = max(int(h * (resize_width / max(w, 1))), 1)
            resized = cv2.resize(frame, (resize_width, new_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)

            if prev_gray is None:
                diff = 0.0
            else:
                frame_diff = cv2.absdiff(gray, prev_gray)
                diff = float(cv2.mean(frame_diff)[0] / 255.0)

            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            edges = cv2.Canny(gray, 80, 180)
            total_pixels = max(edges.shape[0] * edges.shape[1], 1)
            text_density = float(cv2.countNonZero(edges) / total_pixels)

            features.append(
                FrameFeature(
                    ts=round(ts, 3),
                    diff=diff,
                    sharpness=sharpness,
                    hash_hex=_dhash_hex(gray),
                    text_density=text_density,
                )
            )

            prev_gray = gray
            sampled_count += 1
            if logger is not None and sampled_count % progress_every_samples == 0:
                elapsed = perf_counter() - start_time
                avg_ms = (elapsed / max(sampled_count, 1)) * 1000.0
                logger.info(
                    "[extract] sampled=%s decoded=%s video_ts=%.1fs avg=%.2fms/sample elapsed=%.2fs",
                    sampled_count,
                    frame_index + 1,
                    ts,
                    avg_ms,
                    elapsed,
                )
            frame_index += 1
    finally:
        capture.release()

    if logger is not None:
        elapsed = perf_counter() - start_time
        avg_ms = (elapsed / max(sampled_count, 1)) * 1000.0
        logger.info(
            "[extract] done sampled=%s decoded=%s avg=%.2fms/sample elapsed=%.2fs",
            sampled_count,
            frame_index,
            avg_ms,
            elapsed,
        )

    return features


def write_images_for_records(
    video_path: str | Path,
    *,
    timestamps_to_paths: list[tuple[float, Path]],
) -> None:
    """Decode and save RGB frames at requested timestamps."""
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"unable to open video: {video_path}")

    try:
        for ts, output_path in timestamps_to_paths:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(ts, 0.0) * 1000.0)
            ok, frame = capture.read()
            if not ok:
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), frame)
    finally:
        capture.release()
