# Module: deliverables

## Purpose

把 timeline 转成用户可消费文档：转译稿、图文笔记、摘要。

## Inputs

- `fusion/timeline.json`
- `frame_summary/frame_summary.jsonl` (frame-level free-text summaries, optional direct evidence)

## Outputs

- `outputs/clean_transcript.md`
- `outputs/illustrated_notes.md`
- `outputs/summary.json`
- `outputs/export.html` (optional)

## Options

- A: same-language cleanup
- B: optional translation
- C: concise summary (prefer ASR + VLM frame summaries)
- D: image placeholder and post-fill

## Params

- summary length range
- style profile
- placeholder policy

## Metrics

- unresolved placeholders
- missing chunk ratio
- output length/section count

## Failure & Fallback

- regenerate failed sections by chunk
- keep partial outputs with explicit warnings
