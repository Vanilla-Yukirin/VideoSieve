# Documentation Index

## Overview

- `docs/ARCHITECTURE.md` - 架构总览（目的、组件、数据流、目录结构、关键决策）

## Vision

- `docs/00_vision/goals-and-nongoals.md`
- `docs/00_vision/roadmap-milestones.md`

## System Contracts

- `docs/10_system/data-contracts.md`
- `docs/10_system/state-machine.md`
- `docs/10_system/events-and-websocket.md`
- `docs/10_system/configuration.md`
- `docs/10_system/artifact-realtime-plan.md`
- `docs/10_system/workspace-layout.md`

## Modules

- `docs/20_modules/ingest.md`
- `docs/20_modules/hotwords.md`
- `docs/20_modules/asr.md`
- `docs/20_modules/keyframes.md`
- `docs/20_modules/frame-summary.md`
- `docs/20_modules/fusion.md`
- `docs/20_modules/deliverables.md`
- `docs/20_modules/pipeline-orchestrator.md`

## Apps

- `docs/30_apps/api.md`
- `docs/30_apps/web.md`
- `docs/30_apps/workers.md`

## Ops

- `docs/40_ops/deployment.md`
- `docs/40_ops/observability.md`
- `docs/40_ops/troubleshooting.md`
- `docs/40_ops/security-and-secrets.md`

## Decisions

- `docs/adr/ADR-0001-architecture-boundary.md`
- `docs/adr/ADR-0002-control-protocol-and-safe-points.md`
- `docs/adr/ADR-0003-workspace-lifecycle.md`
- `docs/adr/ADR-0004-redis-event-bus.md`

## Archive

- `docs/ARCHITECTURE-old.md`（历史长版，仅追溯）
- `docs/ARCHITECTURE-rewrite.md`（历史重写草稿，仅对比）

## Rule of Maintenance

- `docs/ARCHITECTURE.md` 是当前架构基线。
- 任何跨模块契约变更，先改 `docs/10_system/*` 与 ADR，再改代码。
