# Module: fusion

## Purpose

把 ASR、关键帧、OCR 统一组装为 `timeline.json`。

## Inputs

- `asr/transcript.jsonl`
- `frames/keyframes.jsonl`
- `ocr/ocr.jsonl`

## Outputs

- `fusion/timeline.json`

## Options

- A: time-window alignment
- B: keyframe as chapter boundary
- C: explicit evidence chain

## Params

- alignment window delta
- chunk split strategy

## Metrics

- chunk coverage
- subtitle/frame mismatch ratio

## Failure & Fallback

- widen alignment window
- fallback to transcript-only chunking when visual signals are sparse
