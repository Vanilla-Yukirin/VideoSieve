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

## Options

- A: online ASR (default)
- B: local CPU ASR (fallback)
- C: low-confidence segment repair

## Params

- chunk size
- confidence threshold
- retry policy

## Metrics

- confidence distribution
- hotword hit rate
- tail alignment drift

## Failure & Fallback

- provider retry and checkpoint resume
- selective re-transcription for low confidence segments
