# Observability

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
