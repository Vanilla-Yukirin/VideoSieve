# Module: ocr

## Purpose

提取关键帧文字，为笔记和摘要提供证据。

## Inputs

- `frames/images/*.jpg`

## Outputs

- `ocr/ocr.jsonl`

## Current Implementation

- Implemented as adapter pattern: `OCRProvider` interface + pluggable provider
- Baseline provider is `MockOCRProvider` for deterministic local integration testing
- Runtime flow reads `frames/keyframes.jsonl`, then writes one JSONL row per selected frame to `ocr/ocr.jsonl`
- Output fields follow current contract baseline: `schema_version`, `frame_id`, `lang`, `conf`, `blocks[]`
- Current `blocks[]` contains `text`, `bbox`, `conf`; real provider integration keeps the same envelope

## Options

- A: OCR-only (default)
- B: VLM supplement
- C: OCR + VLM hybrid

## Params

- `language_hint` (default `None`): language passed to provider (baseline demo often sets `zh`)
- `provider` (default `MockOCRProvider`): OCR adapter implementation used by `OCRBaselineService`

## Metrics

- text block count per frame
- low-confidence ratio
- OCR coverage ratio

## Failure & Fallback

- trigger higher resolution source
- apply ROI/crop/scale pre-processing
