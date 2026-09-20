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
- `outputs/deliverables.ready.json`（最后发布的 generation readiness manifest）

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

## Publishing and Failure

- 严格校验 timeline 与 frame evidence 的 schema、身份、时间范围、引用和 source id；
- clean transcript、illustrated notes 和可选 summary 先写 generation staging 文件；
- 全部文件及其 SHA-256/大小通过后，逐个发布 canonical 文件，最后发布 manifest；
- 任一步失败会删除 manifest、canonical 和 staging，API 不把半套或旧输出列为 ready；
- `summary.json` 保存输入、配置、prompt、provider/model、覆盖率和调用轮次 provenance，
  不保存 API key。
