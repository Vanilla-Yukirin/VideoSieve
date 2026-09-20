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
- `accepted` 只表示请求已持久化；worker 到达安全点并确认后才是 `applied`。
- `pause_requested/cancel_requested` 是请求态，不能冒充 `paused/cancelled` 执行确认态。
- 心跳超时最多进入 `interrupted`，不能自动重复领取仍可能运行的任务。

## Alternatives Considered

- Celery 强制 terminate 作为默认：简单但高风险。
- 在 API 进程内直接改状态：无法证明计算实际停止。

## Consequences

- Positive: 可预测、可清理、可恢复。
- Negative: 需要在长步骤中显式埋安全点。
