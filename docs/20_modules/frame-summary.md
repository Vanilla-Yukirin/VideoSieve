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
- Web Provider 设置中的 endpoint、model、prompt、concurrency、RPM；
- Web 中录入并由 `APP_SECRET_KEY` 加密持久化的 credential；
- job snapshot 中冻结非敏感参数和 credential reference，不保存 API key 明文；
- `QWEN_API_KEY` 仅兼容仍引用该 credential name 的旧 snapshot，不是新用户入口。

## Metrics

- per-frame response success ratio
- per-frame latency
- non-empty description ratio

## Failure Semantics

- 缺配置、缺 key、网络、HTTP、畸形响应和空响应均产生带 code/hint/retryable 的失败；
- 不写 offline placeholder，也不把失败帧包装成成功 JSONL；
- 输出先写临时文件，全部请求成功并校验后再替换 canonical 文件；
- test provider 只能通过测试依赖注入使用。

## Readiness Boundary

- 设置完整只表示 `configured`；当前尚未实现独立的 VLM 连接／最小视觉调用测试；
- endpoint 可访问或普通文本模型可调用，也不能证明所选模型支持图片输入；
- 真实关键帧返回非空合法描述才证明当次调用成功，真实视频内容质量仍需人工复核。
