# ADR-0005: Single-host SQLite Queue and Independent Worker

## Status

Accepted and implemented on 2026-09-20. Automated unit, contract and process-level
integration coverage exists; real-provider end-to-end acceptance remains a separate gate.

## Context

VideoSieve 的确认部署范围是一台电脑或服务器，供个人或少量用户使用。现有代码在
FastAPI 进程内使用后台线程执行 job，事件仅能在内存路径分发；旧文档提出的
Celery + Redis 并未成为可用运行时。

任务需要在 API 重启后继续存在，并支持排队、独立执行、进度、事件重放、暂停、取消、
恢复和本地大文件产物。当前规模不要求多节点调度或高可用。

## Decision

采用以下单机架构：

- FastAPI 负责认证、WebSocket 会话、命令持久化和受限 HTTP 文件传输；
- SQLite 保存持久队列、确认状态、控制请求、attempt、stage、事件和产物索引；
- 一个独立 Python worker 进程轮询并原子领取任务；
- 本地 workspace 保存媒体、中间数据和最终产物；
- WebSocket 承担业务快照、命令、确认与增量事件；
- HTTP 仅承担页面／初始会话引导、上传、下载及健康检查；
- 首版不使用 Celery 或 Redis。

SQLite 使用本机磁盘、WAL、连接级外键检查、busy timeout 和短事务。API 与 worker
各自使用连接，并按写入职责更新数据库。视频处理与外部模型调用必须在事务之外。

控制请求和确认状态分离。API 接受 pause/cancel 不代表计算已经停止；worker 到达
安全点并完成必要保存／清理后，才能确认 paused/cancelled。

事件以 SQLite 中单调递增的 `event_id` 持久化。客户端携带游标重连，服务端在保留期内
重放事件并发送带 `state_version` 的权威快照。内存通知只允许作为延迟优化。

## Supersedes

- [ADR-0004](ADR-0004-redis-event-bus.md) 的 Redis Pub/Sub/Streams 目标。
- `ARCHITECTURE-old.md` 与 `ARCHITECTURE-rewrite.md` 中的 Celery + Redis 默认方案。

历史文件保留用于追溯，不据此继续实现 Redis/Celery。

## Alternatives Considered

### Celery + Redis

适合多 worker、多节点和成熟 broker 语义，但为当前单机规模增加两个运行部件、部署和
故障模式，Windows 本地开发也更复杂。当前没有证据证明这些成本必要。

### API 进程内后台线程

实现简单，但 API 生命周期与计算任务耦合，无法提供可靠的持久领取、进程级恢复和
实际停止确认。

### SQLite 内执行计算

不可行。SQLite 只协调短事务；FFmpeg、ASR、VLM 和 LLM 由 worker 在事务外执行。

### 服务端数据库或通用工作流引擎

能提供更强并发或编排能力，但当前需求不足以抵消部署和维护成本。

## Consequences

Positive:

- 运行部件少，适合单机和本地磁盘；
- 队列、状态与事件可持久化和审计；
- API 与计算任务生命周期分离；
- 无需维护 Redis/Celery 双栈。

Negative:

- SQLite 同一时刻只有一个写者，必须限制写事务和事件频率；
- 单机不提供多节点高可用；
- 需要自行实现领取、心跳、失联判定、重放和恢复规则；
- 外部模型调用不能保证 exactly-once。

## Revisit Triggers

出现以下经过测量的需求时，重新评估服务端数据库与消息队列：

- 需要多台计算节点；
- SQLite 写锁等待持续成为瓶颈；
- 需要服务级高可用或跨主机故障转移；
- 单 worker 无法满足已确认的吞吐目标。

重新评估必须形成新 ADR，不在本决策上隐式叠加 Redis 或 Celery。
