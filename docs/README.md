# VideoSieve 文档索引

## 阅读顺序

1. [ARCHITECTURE.md](ARCHITECTURE.md)：当前单机目标架构与现状边界；
2. [rebuild-plan.md](00_vision/rebuild-plan.md)：已核查缺陷、实施阶段与验收要求；
3. `10_system/`：跨模块权威契约；
4. `20_modules/` 与 `30_apps/`：模块和运行单元职责；
5. `adr/`：已经接受或被替代的架构决策；
6. `40_ops/`：部署、观测、安全与排障。

文档中必须区分：

- **Current**：从当前代码观察到的行为，仍不等于真实端到端验收；
- **Target**：已接受的设计契约，代码可能尚未实现；
- **Verified**：对应代码版本已通过文档所述的实际验证；
- **Historical/Superseded**：仅供追溯，不能指导新实现。

## Overview

- [单机重做方案](00_vision/rebuild-plan.md)：2026-09-20 核查结果与分阶段重做建议；
- [架构基线](ARCHITECTURE.md)：FastAPI + SQLite + 独立 Python worker + 本地文件系统 + WebSocket；
- [质量与验证](QUALITY.md)：仓库 harness、质量门槛和证据要求。

## Vision

- [Goals and non-goals](00_vision/goals-and-nongoals.md)
- [Roadmap and milestones](00_vision/roadmap-milestones.md)

## System Contracts

- [Data contracts](10_system/data-contracts.md)
- [Job state machine](10_system/state-machine.md)
- [Events and WebSocket](10_system/events-and-websocket.md)
- [Configuration](10_system/configuration.md)
- [Workspace layout](10_system/workspace-layout.md)
- [Artifact realtime plan](10_system/artifact-realtime-plan.md)（已被当前 WS cursor 契约替代，保留追溯）

`state-machine.md`、`events-and-websocket.md` 和 `configuration.md` 是调度与控制改造的
权威语义。代码、测试或其他文档与之冲突时，应先通过 ADR 修订契约，不能静默偏离。

## Modules

- [Ingest](20_modules/ingest.md)
- [Hotwords](20_modules/hotwords.md)
- [ASR](20_modules/asr.md)
- [Keyframes](20_modules/keyframes.md)
- [Frame summary](20_modules/frame-summary.md)
- [Fusion](20_modules/fusion.md)
- [Deliverables](20_modules/deliverables.md)
- [Pipeline orchestrator](20_modules/pipeline-orchestrator.md)

## Apps

- [API](30_apps/api.md)
- [Web](30_apps/web.md)
- [Worker](30_apps/workers.md)

## Operations

- [Windows 本机部署](40_ops/local-windows.md)
- [Deployment](40_ops/deployment.md)
- [Observability](40_ops/observability.md)
- [Troubleshooting](40_ops/troubleshooting.md)
- [Security and secrets](40_ops/security-and-secrets.md)

## Decisions

- [ADR-0001: architecture boundary](adr/ADR-0001-architecture-boundary.md)
- [ADR-0002: control protocol and safe points](adr/ADR-0002-control-protocol-and-safe-points.md)
- [ADR-0003: workspace lifecycle](adr/ADR-0003-workspace-lifecycle.md)
- [ADR-0004: Redis event bus](adr/ADR-0004-redis-event-bus.md)（Superseded，未实施）
- [ADR-0005: single-host SQLite queue and worker](adr/ADR-0005-single-host-sqlite-worker.md)（Accepted，已实现；真实模型验收待执行）
- [ADR-0006: external ASR through CapsWriter WebSocket](adr/ADR-0006-external-asr-capswriter-websocket.md)（Accepted，已实现；真实服务验收待执行）
- [ADR-0007: Web-managed provider credentials](adr/ADR-0007-web-provider-credentials.md)（Accepted；连接测试待实现）
- [ADR-0008: single-host trusted mode](adr/ADR-0008-single-host-trusted-mode.md)（Accepted；产品内无登录，远程访问由外层控制）

## Archive

- [ARCHITECTURE-old.md](ARCHITECTURE-old.md)：旧 Celery + Redis 长方案；
- [ARCHITECTURE-rewrite.md](ARCHITECTURE-rewrite.md)：旧重写草稿。

归档文件保持原样用于追溯，不把其中的技术选型、状态或命令当作当前事实。

## Maintenance Rules

- 跨模块行为先同步系统契约和 ADR，再实现代码与测试；
- 每个“已实现”结论都要能指向代码和对应测试，模型能力还需真实输入验收；
- 旧方案被替代时保留历史文件或把 ADR 标成 Superseded，不抹除决策背景；
- 文档检查只能证明格式与引用一致，不能证明服务、worker 或模型链路可用。
