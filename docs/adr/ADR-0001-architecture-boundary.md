# ADR-0001: apps/packages/workers/infra Boundary

## Status

Accepted

## Context

需要清晰隔离可部署单元、业务逻辑与外部依赖，避免耦合扩散。

## Decision

采用 `apps/`、`packages/`、`workers/`、`packages/infra` 四层边界。

## Alternatives Considered

- 单体目录混放：实现快但后续演进困难。

## Consequences

- Positive: 分层清晰、便于测试与替换。
- Negative: 初期目录与文档成本略高。
