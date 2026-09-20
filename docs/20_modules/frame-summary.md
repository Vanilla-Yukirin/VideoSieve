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
- `QWEN_API_KEY`（secret 环境变量）
- job snapshot 中冻结的 base URL、model、prompt、concurrency、RPM

## Metrics

- per-frame response success ratio
- per-frame latency
- non-empty description ratio

## Failure Semantics

- 缺配置、缺 key、网络、HTTP、畸形响应和空响应均产生带 code/hint/retryable 的失败；
- 不写 offline placeholder，也不把失败帧包装成成功 JSONL；
- 输出先写临时文件，全部请求成功并校验后再替换 canonical 文件；
- test provider 只能通过测试依赖注入使用。
