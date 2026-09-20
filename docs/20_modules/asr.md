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
- Bearer Token 是 WebSocket 握手头的选填项。worker 只从 `CAPSWRITER_TOKEN` 读取，
  SQLite 和 job snapshot 只保存 credential name；
- 未知、空、`mock`、`baseline` 或已删除的 `funasr_local` 明确拒绝；
- 测试替身位于 `tests/support.py`，不属于生产包。

## Params

- WebSocket endpoint、language、context 和 timeout；
- WebSocket 分块与重叠参数遵循 CapsWriter 文件转写协议；
- ffmpeg executable；
- retry policy。

## Metrics

- confidence distribution
- hotword hit rate
- tail alignment drift

## Failure Semantics

- 未配置、FFmpeg 解码、连接、超时或 provider 输出错误会使 ASR stage 失败；
- 不生成模拟 transcript，不把缺配置解释为成功；
- CapsWriter 不提供置信度时，canonical segment 的 `conf` 写为 `0.0`，同时 metadata 明确
  标记 `confidence_available=false`，不能把该值解释为模型给出的低置信度；
- 真实转写质量、时间戳和热词效果需要 real-model evidence 及人工复核。
