# Module: ocr

## Purpose

使用 VLM 对关键帧做一次自由文本理解，直接产出“画面描述 + 可见文字提取”。

## Inputs

- `frames/images/*.jpg`

## Outputs

- `ocr/ocr.jsonl`

## Current Implementation

- Implemented as adapter pattern: `OCRProvider` interface + `VLMOnlyProvider`
- Runtime flow reads `frames/keyframes.jsonl`, then writes one JSONL row per selected frame to `ocr/ocr.jsonl`
- One frame triggers one VLM request with a free-text prompt (no mandatory JSON response)
- Output keeps baseline envelope and adds VLM metadata fields: `provider`, `summary_text`

## Options

- A: VLM-only (default)

## Params

- `language_hint` (default `None`): language passed to provider (baseline demo often sets `zh`)
- `provider` (default `VLMOnlyProvider`): VLM adapter implementation used by `OCRBaselineService`
- `QWEN_API_KEY` / `QWEN_BASE_URL` / `VLM_MODEL` / `VLM_TIMEOUT_SECONDS`: runtime provider config

## Metrics

- per-frame response success ratio
- per-frame latency
- non-empty summary ratio

## Failure & Fallback

- network/API failure returns offline placeholder text and keeps pipeline moving
- keep full free-text summary in `summary_text` for downstream timeline and deliverables
