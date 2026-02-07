# Module: hotwords

## Purpose

为 ASR 提供可控偏置，提高专有名词命中率。

## Inputs

- `meta/meta.json`

## Outputs

- `hotwords/hotwords.json`
- `hotwords/vocabulary_ref.json` (optional)

## Options

- A: rule-based extraction
- B: model-assisted refinement
- C: user edit in UI

## Params

- max terms
- weight levels
- language split strategy

## Metrics

- hotword hit rate in transcripts
- false hit rate

## Failure & Fallback

- enforce cap and weight tiers to reduce noise
