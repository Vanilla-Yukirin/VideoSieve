# ADR-0002: Control Protocol and Cooperative Safe Points

## Status

Accepted

## Context

需要支持 pause/resume/cancel/delete，同时保证运行中任务可控且不破坏数据一致性。

## Decision

采用 WebSocket 控制协议 + worker 协作式安全点检查。

补充约束：
- 命令合法性以 `docs/10_system/state-machine.md` 的 Command x JobState 矩阵为准。
- 非法转移必须返回明确错误码（例如 `INVALID_STATE_TRANSITION`）。

## Alternatives Considered

- Celery 强制 terminate 作为默认：简单但高风险。

## Consequences

- Positive: 可预测、可清理、可恢复。
- Negative: 需要在长步骤中显式埋安全点。
