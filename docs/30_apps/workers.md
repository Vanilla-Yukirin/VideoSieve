# App: workers

## Purpose

作为 Celery worker 运行入口，消费任务并触发 pipeline。

## Responsibilities

- bootstrap runtime dependencies
- task discovery and registration
- invoke pipeline stages
- publish events/logs

## Control Behavior

- cooperative pause/cancel checks at safety points
- graceful shutdown and cleanup hooks

## Safety Point Minimum Requirements

- check control flag before and after external process calls (e.g. `ffmpeg`, `yt-dlp`)
- in long loops, check at least every `N` seconds or every `M` items/frames
- check before and after external API calls to avoid unnecessary spend
- `cancel` uses soft-cancel first; if timeout exceeded, escalate to hard terminate with explicit cleanup log

## Alignment Notes

- command semantics must follow `docs/10_system/state-machine.md` matrix
- worker acknowledgements should map to WS `control_ack` event contract
