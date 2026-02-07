# Module: ocr

## Purpose

提取关键帧文字，为笔记和摘要提供证据。

## Inputs

- `frames/images/*.jpg`

## Outputs

- `ocr/ocr.jsonl`

## Options

- A: OCR-only (default)
- B: VLM supplement
- C: OCR + VLM hybrid

## Params

- min confidence
- language hints
- image pre-processing toggles

## Metrics

- text block count per frame
- low-confidence ratio
- OCR coverage ratio

## Failure & Fallback

- trigger higher resolution source
- apply ROI/crop/scale pre-processing
