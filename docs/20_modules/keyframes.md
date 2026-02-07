# Module: keyframes

## Purpose

抽取信息密度高、适合 OCR/笔记的代表帧。

## Inputs

- `media/source.mp4`

## Outputs

- `frames/keyframes.jsonl`
- `frames/images/*.jpg`
- `frames/metrics/diff_curve.csv`

## Options

- A: stable-frame
- B: ROI-stable
- C: scene-cut supplement
- D: clustering fallback
- E: hybrid strategy

## Params

- sample fps
- stability threshold
- min stable window
- dedup interval

## Metrics

- keyframe count and interval
- duplicate ratio
- reason distribution (`stable/scene/cluster/sample`)

## Failure & Fallback

- auto relax threshold when output too small
- fallback to periodic sampling
