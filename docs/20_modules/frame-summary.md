# Module: frame_summary

## Purpose

对每张关键帧生成一段自由文本画面描述，用于后续时间线与产物生成。

## Inputs

- `frames/images/*.jpg`

## Outputs

- `frame_summary/frame_summary.jsonl`

## Current Implementation

- Implemented as adapter pattern: `FrameSummaryProvider` interface + `QwenFrameSummaryProvider`
- Runtime flow reads `frames/keyframes.jsonl`, then writes one JSONL row per selected frame to `frame_summary/frame_summary.jsonl`
- One frame triggers one VLM request and stores free-text output directly

## Params

- `language_hint` (default `None`)
- `provider` (default `QwenFrameSummaryProvider`)
- `QWEN_API_KEY` / `QWEN_BASE_URL` / `VLM_MODEL` / `VLM_TIMEOUT_SECONDS`

## Metrics

- per-frame response success ratio
- per-frame latency
- non-empty description ratio

## Failure & Fallback

- network/API failure returns offline placeholder text and keeps pipeline moving
