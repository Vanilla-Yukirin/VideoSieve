"""Algorithmic keyframe selection from sampled frame features."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class FrameFeature:
    """Per-frame feature set used by keyframe algorithms."""

    ts: float
    diff: float
    sharpness: float
    hash_hex: str
    text_density: float = 0.0


@dataclass(frozen=True)
class CandidateFrame:
    """Candidate frame after stable-segment detection."""

    ts: float
    hash_hex: str
    sharpness: float
    stability: float
    text_density: float
    reason: str


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [1.0 for _ in values]
    return [(value - lo) / (hi - lo) for value in values]


def _hex_to_bits(value: str) -> str:
    return "".join(f"{int(char, 16):04b}" for char in value)


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Compute Hamming distance between two hex digest strings."""
    bits_a = _hex_to_bits(hash_a)
    bits_b = _hex_to_bits(hash_b)
    if len(bits_a) != len(bits_b):
        raise ValueError("hash lengths must be equal")
    return sum(left != right for left, right in zip(bits_a, bits_b, strict=True))


def detect_stable_segments(
    frames: list[FrameFeature],
    *,
    lookback: int = 12,
    mad_scale: float = 3.0,
    min_stable_len: int = 4,
) -> list[tuple[int, int]]:
    """Find stable frame index ranges using adaptive median+MAD threshold."""
    if not frames:
        return []
    if min_stable_len <= 0:
        raise ValueError("min_stable_len must be > 0")

    stable_flags: list[bool] = []
    diffs = [frame.diff for frame in frames]
    for idx, diff in enumerate(diffs):
        start = max(0, idx - lookback + 1)
        window = diffs[start : idx + 1]
        med = median(window)
        deviations = [abs(value - med) for value in window]
        mad = median(deviations)
        threshold = med + (mad_scale * mad)
        stable_flags.append(diff <= threshold)

    segments: list[tuple[int, int]] = []
    seg_start: int | None = None
    for idx, is_stable in enumerate(stable_flags):
        if is_stable and seg_start is None:
            seg_start = idx
        if not is_stable and seg_start is not None:
            if idx - seg_start >= min_stable_len:
                segments.append((seg_start, idx - 1))
            seg_start = None
    if seg_start is not None and len(frames) - seg_start >= min_stable_len:
        segments.append((seg_start, len(frames) - 1))
    return segments


def build_stable_candidates(
    frames: list[FrameFeature],
    segments: list[tuple[int, int]],
) -> list[CandidateFrame]:
    """Pick one representative frame from each stable segment."""
    candidates: list[CandidateFrame] = []
    for seg_start, seg_end in segments:
        segment = frames[seg_start : seg_end + 1]
        segment_sharpness = [frame.sharpness for frame in segment]
        median_index = (len(segment) - 1) // 2
        med_frame = segment[median_index]
        sharp_norm = _normalize(segment_sharpness)
        if sharp_norm[median_index] < 0.6:
            chosen_index = max(range(len(segment)), key=lambda idx: segment[idx].sharpness)
            chosen = segment[chosen_index]
        else:
            chosen = med_frame

        segment_diff = [frame.diff for frame in segment]
        stability = 1.0 - (_normalize(segment_diff)[segment.index(chosen)])
        candidates.append(
            CandidateFrame(
                ts=chosen.ts,
                hash_hex=chosen.hash_hex,
                sharpness=chosen.sharpness,
                stability=max(0.0, min(stability, 1.0)),
                text_density=chosen.text_density,
                reason="stable",
            )
        )
    return candidates


def score_candidates(
    candidates: list[CandidateFrame],
    *,
    w_stable: float = 0.45,
    w_sharp: float = 0.30,
    w_text: float = 0.25,
) -> dict[float, float]:
    """Compute base score for each candidate timestamp."""
    if not candidates:
        return {}
    sharpness_norm = _normalize([candidate.sharpness for candidate in candidates])
    text_norm = _normalize([candidate.text_density for candidate in candidates])
    scores: dict[float, float] = {}
    for idx, candidate in enumerate(candidates):
        score = (
            w_stable * candidate.stability + w_sharp * sharpness_norm[idx] + w_text * text_norm[idx]
        )
        scores[candidate.ts] = score
    return scores


def select_with_constraints(
    candidates: list[CandidateFrame],
    *,
    base_scores: dict[float, float],
    min_gap_seconds: float,
    fallback_gap_seconds: float,
    duration_seconds: float,
    min_hash_dist: int = 8,
    k_max: int | None = None,
) -> list[CandidateFrame]:
    """Select candidates by score with hard min-gap and fallback coverage."""
    if min_gap_seconds <= 0:
        raise ValueError("min_gap_seconds must be > 0")
    if fallback_gap_seconds <= 0:
        raise ValueError("fallback_gap_seconds must be > 0")
    if min_hash_dist < 0:
        raise ValueError("min_hash_dist must be >= 0")

    by_time = sorted(candidates, key=lambda item: item.ts)
    selected: list[CandidateFrame] = []

    bucket_start = 0.0
    while bucket_start < duration_seconds:
        bucket_end = bucket_start + fallback_gap_seconds
        in_bucket = [item for item in by_time if bucket_start <= item.ts < bucket_end]
        if in_bucket:
            in_bucket.sort(key=lambda item: base_scores.get(item.ts, 0.0), reverse=True)
            for item in in_bucket:
                if all(abs(item.ts - existing.ts) >= min_gap_seconds for existing in selected):
                    if any(
                        hamming_distance(item.hash_hex, existing.hash_hex) < min_hash_dist
                        for existing in selected
                    ):
                        continue
                    selected.append(item)
                    break
        bucket_start = bucket_end

    remaining = [item for item in by_time if item not in selected]
    remaining.sort(key=lambda item: base_scores.get(item.ts, 0.0), reverse=True)

    for item in remaining:
        if k_max is not None and len(selected) >= k_max:
            break
        if any(abs(item.ts - existing.ts) < min_gap_seconds for existing in selected):
            continue
        if any(
            hamming_distance(item.hash_hex, existing.hash_hex) < min_hash_dist
            for existing in selected
        ):
            continue
        novelty = 1.0
        if selected:
            distances = [hamming_distance(item.hash_hex, frame.hash_hex) for frame in selected]
            novelty = min(1.0, (min(distances) / max(len(item.hash_hex) * 4, 1)))
        if base_scores.get(item.ts, 0.0) + (0.25 * novelty) < 0.35:
            continue
        selected.append(item)

    return sorted(selected, key=lambda item: item.ts)
