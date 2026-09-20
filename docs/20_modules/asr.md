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

## Current Provider

- 生产默认 `funasr_local`，由 `VIDEOSIEVE_ASR_*` 配置模型、hub、device 和语言；
- 未知、空、`mock` 或 `baseline` provider 明确拒绝；
- 测试替身位于 `tests/support.py`，不属于生产包。

## Params

- chunk size
- confidence threshold
- retry policy

## Metrics

- confidence distribution
- hotword hit rate
- tail alignment drift

## Failure Semantics

- 模型依赖、加载、媒体输入或 provider 输出错误会使 ASR stage 失败；
- 不生成模拟 transcript，不把缺配置解释为成功；
- 真实转写质量、时间戳和热词效果需要 real-model evidence 及人工复核。
