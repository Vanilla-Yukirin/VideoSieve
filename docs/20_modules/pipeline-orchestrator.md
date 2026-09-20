# Module: pipeline-orchestrator

## Purpose

负责 stage 编排、断点续跑、控制命令安全点和恢复判定。队列领取由独立 worker
入口负责；本模块不依赖 Celery 或 Redis。

## Inputs

- Project/Job records
- config snapshot
- immutable job config snapshot
- control requests and attempt ownership from SQLite

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

- only reuse a successful stage when input/config fingerprints and artifacts validate
- cancel-safe cleanup for temporary resources
- heartbeat timeout produces `interrupted`; it never auto-starts a second attempt
