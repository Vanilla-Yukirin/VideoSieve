# Module: keyframes

## Purpose

抽取信息密度高、适合画面语义总结/笔记的代表帧。

## Inputs

- `media/source.mp4`

## Outputs

- `frames/keyframes.jsonl`
- `frames/images/*.jpg`
- `frames/metrics/diff_curve.csv`
- `frames/metrics/selection_trace.jsonl` (optional diagnostics)
- `frames/metrics/timing_report.json` (optional diagnostics)

## Current Implementation

- Baseline pipeline: `extract features -> stable segments -> candidates -> constrained selection`
- Feature extraction currently uses OpenCV (`diff`, `sharpness`, `dhash`, `text_density`)
- Stable detection uses adaptive threshold (`median + MAD`) with minimum stable run length
- Candidate selection enforces hard `min_gap_seconds` and hash-distance dedup (`min_hash_dist`)
- Coverage fallback ensures each `fallback_gap_seconds` window has at least one candidate when possible
- Current output `reason` is mainly `stable`; fallback candidates use `sample` (both within contract set)

## Options

- A: stable-frame
- B: ROI-stable
- C: scene-cut supplement
- D: clustering fallback
- E: hybrid strategy

## Params

- `sample_fps` (default `3.0`): extraction sampling rate; lower is faster, higher captures more transitions
- `min_gap_seconds` (default `2.0`): hard minimum time gap between selected frames
- `fallback_gap_seconds` (default `12.0`): coverage window size for fallback sampling
- `min_hash_dist` (default `8`): minimum Hamming distance for dedup; higher value removes more near-duplicates
- `stable_lookback` (default `12`): sliding window size used in adaptive stability threshold
- `stable_mad_scale` (default `3.0`): sensitivity of `median + MAD`; lower is stricter for stable detection
- `min_stable_len` (default `4`): minimum consecutive stable sampled frames required to form a stable segment
- `k_max` (default `200`): upper limit for selected keyframe count
- `extract_progress_every` (default `150`): progress log interval during feature extraction (observability only)

## Metrics

- keyframe count and interval
- duplicate ratio
- reason distribution (`stable/scene/cluster/sample`)

## Failure & Fallback

- auto relax threshold when output too small
- fallback to periodic sampling
