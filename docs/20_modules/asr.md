# Module: asr

## Purpose

生成带时间戳的字幕段落，作为后续对齐基线。

## Inputs

- `media/audio.wav`
- `hotwords/hotwords.json`
- language hint

## Outputs

- `asr/transcript.jsonl`
- `asr/transcript.words.jsonl` (optional)

## Current Providers

- 生产默认 `unconfigured`，必须显式选择外部 provider；
- `capswriter` 默认实现上游根 WebSocket 协议：发送 Base64 编码的 float32、16 kHz、
  单声道音频消息，接收最终文本、token 和时间戳；
- Bearer Token 是 WebSocket 握手头的选填项。操作者在 Web Provider 设置中录入，服务端
  使用 `APP_SECRET_KEY` 加密持久化；job snapshot 只保存 credential reference；
- `CAPSWRITER_TOKEN` 环境变量只用于解析仍引用该名称的旧 job snapshot，不是新用户
  配置入口；
- 未知、空、`mock`、`baseline` 或已删除的 `funasr_local` 明确拒绝；
- 测试替身位于 `tests/support.py`，不属于生产包。

下拉框选择 provider，不单独暴露 transport 开关。协议由 adapter 自己封装：
`CapsWriter（WS）` 固定使用官方 WebSocket；未来接入普通 HTTP ASR API 时新增对应
provider adapter 和选项，不改变 CapsWriter 的协议。

## Params

- WebSocket endpoint、language、context 和 timeout；
- `seg_duration` / `seg_overlap` 默认采用上游文件转录客户端的 `60 / 4` 秒；协议
  dataclass 的 fallback 是 `15 / 2` 秒。adapter 和不可变 job snapshot 保留显式参数，
  后续调优不会改变已创建任务；
- ffmpeg executable；
- retry policy。

## Metrics

- confidence distribution
- hotword hit rate
- tail alignment drift

## Failure Semantics

- 未配置、FFmpeg 解码、连接、超时或 provider 输出错误会使 ASR stage 失败；
- 不生成模拟 transcript，不把缺配置解释为成功；
- CapsWriter 不提供置信度时，canonical segment 省略可选的 `conf`，同时 metadata 明确
  标记 `confidence_available=false`；前端不会显示虚假的 `0%`；
- 真实转写质量、时间戳和热词效果需要 real-model evidence 及人工复核。

## Readiness Boundary

- `configured` 只表示 provider、endpoint 与所需 credential 已保存；
- 当前尚未实现独立的 CapsWriter 握手／连接测试，不能把 `configured` 显示成
  `reachable` 或 `verified`；
- 只有真实音频得到合法转写，才能证明当次 ASR 调用成功；仍需用真实视频检查内容、
  时间戳和热词效果，才能完成端到端验收。
