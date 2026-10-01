# Observability

## Model requests (implemented)

`jobs/{job_id}/meta/model_calls.jsonl` records every request attempt, including failures
and retries. Counters come only from provider `usage`; historical jobs and missing
values are never estimated. No credential, endpoint, prompt or response text is stored.
Rows are independently decoded and parsed. A crash tail with incomplete UTF-8 or
JSON is ignored for aggregation while its original bytes remain on disk; restart
appends valid rows after a newline without losing the complete history.

The job page receives `model_usage` WS events; reconnect snapshots rebuild from the
journal. Stage input/output/cache/reasoning totals mark partial sums with an asterisk.
Usage events merge by cursor and nondecreasing call count even if a concurrent
pause/cancel acknowledgement already advanced the task state version.
Cache/reasoning are subsets, not additions. Monotonic per-request time includes the
network; concurrent times overlap, so their sum is neither job wall time nor TTFT.
Retry backoff and RPM-gate waits are excluded from per-request duration.
Anthropic `output_tokens_details.thinking_tokens` is displayed as reasoning tokens,
including an explicitly reported zero; it is not added again to output tokens.

Frame records carry request metadata; overall-summary provenance includes all map,
reduce and final calls. See [ADR-0010](../adr/ADR-0010-model-completion-budgets-and-usage.md).

## Minimum Signals

- project total duration/final state
- stage duration/retry/failure code
- ASR confidence and hotword hit rate
- keyframe count/duplication/diff curve
- frame summary success ratio and latency distribution

## Logs

- structured logs with `project_id`, `job_id`, `stage`
- error logs include `code`, `hint`, `retryable`
- `implemented` operation logs (`operation_logs` table) include:
  `actor_type`, `actor_id`, `action`, `status`, `reason_code`, `meta_json`, `created_at`
- `implemented` rejected/denied actions record explicit `reason_code`
- `implemented` actions written for API control plane include:
  `settings.patch` and job/control operations

## Error-Code Operability

- `implemented` key reason/error codes for monitoring and alert bucketing:
  `validation_error`, `not_found`, `config_error`, `internal_error`
- `planned` add API endpoint for querying operation logs with pagination/filtering.

## UI Rebuild Requirement (Target)

- UI state must be reconstructable from a WebSocket snapshot plus SQLite-persisted cursor events.
- Snapshot is the state truth; events restore incremental history and live updates.
- Snapshot minimum fields: `execution_state`, `requested_action`, `state_version`, current stage,
  progress, `snapshot_event_id`, latest log window and artifact index.
- Client persists the last continuous `event_id`; gaps or expired cursors require an explicit
  `cursor_reset`, never silent continuation.
- `accepted` control acknowledgement and worker-confirmed `applied` must be counted separately.

## Dashboards (Future)

- queue depth
- worker utilization
- oldest queued age and SQLite busy/retry counts
- active/interrupted attempts and heartbeat age
- WebSocket reconnect, cursor replay and cursor reset counts
- failure trend by module/provider
