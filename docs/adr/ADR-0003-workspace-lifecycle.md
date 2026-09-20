# ADR-0003: Workspace Lifecycle and Cleanup

## Status

Accepted

## Context

需要兼顾断点续跑与安全删除，避免产物残留或误删。

## Decision

采用两阶段删除：`cancel` -> wait terminal state -> cleanup。

2026-09-20 补充：

- 重跑创建新 job，不清空旧 job 目录；
- 每个 attempt 使用独立临时目录，校验后原子发布；
- `cancel` accepted 不等于已停止，只有 worker／恢复协调器确认停止后才能 cleanup；
- interrupted job 在确认旧进程退出前禁止清理或复用临时产物。

## Alternatives Considered

- 直接删除：实现简单但会破坏运行一致性。

## Consequences

- Positive: 删除流程安全、可审计。
- Negative: 删除延迟增加。
