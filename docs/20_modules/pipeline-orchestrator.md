# Module: pipeline-orchestrator

## Purpose

负责 stage 编排、并发执行、断点续跑、控制命令生效。

## Inputs

- Project/Job records
- config snapshot
- control flags from DB/Redis

## Outputs

- stage state updates
- job lifecycle events
- retry and failure decisions

## Options

- A: linear pipeline (MVP)
- B: conditional pipeline (mid-term)
- C: stage-level rerun

## Params

- retry count/backoff
- per-stage timeout
- checkpoint strategy

## Metrics

- stage duration
- retry count
- queue depth and worker utilization

## Failure & Fallback

- recover from latest successful stage
- cancel-safe cleanup for temporary resources
