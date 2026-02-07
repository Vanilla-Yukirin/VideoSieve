# ADR-0003: Workspace Lifecycle and Cleanup

## Status

Accepted

## Context

需要兼顾断点续跑与安全删除，避免产物残留或误删。

## Decision

采用两阶段删除：`cancel` -> wait terminal state -> cleanup。

## Alternatives Considered

- 直接删除：实现简单但会破坏运行一致性。

## Consequences

- Positive: 删除流程安全、可审计。
- Negative: 删除延迟增加。
