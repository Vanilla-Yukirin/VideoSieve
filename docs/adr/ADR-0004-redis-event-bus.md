# ADR-0004: Redis Event Bus (Pub/Sub -> Streams)

## Status

Proposed

## Context

实时事件需要先快速上线，同时预留重放与更强可靠性的路径。

## Decision

短期可用 Pub/Sub，目标迁移到 Redis Streams 以支持更好消费语义。

协议约束：
- 无论底层 event bus 模式如何，重连后客户端必须先拉 HTTP snapshot 对齐状态。
- 仅在 Streams（或持久化缓冲）模式下提供 recent events replay。

## Alternatives Considered

- 仅 Pub/Sub：简单但重连重放能力弱。
- 直接 Streams：可靠性更好但实现复杂度更高。

## Consequences

- Positive: 兼顾上线速度与后续演进。
- Negative: 需要维护迁移方案与双栈期。
