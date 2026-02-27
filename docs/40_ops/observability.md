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
  `auth.bootstrap`, `auth.login`, `auth.logout`, `settings.patch`, `guest.job_submit`

## Error-Code Operability

- `implemented` key reason/error codes for monitoring and alert bucketing:
  `auth_required`, `invalid_credentials`, `bootstrap_required`,
  `guest_cookie_key_required`, `guest_cooldown_active`,
  `validation_error`, `not_found`, `config_error`, `internal_error`
- `planned` add API endpoint for querying operation logs with pagination/filtering.

## UI Rebuild Requirement

- UI state must be reconstructable from HTTP snapshot + artifact index without relying on WS replay.
- WS accelerates refresh only; snapshot remains source of truth.
- Snapshot minimum fields: `job status`, `current stage`, `progress`, `latest logs cursor/window`, `artifact list`.

## Dashboards (Future)

- queue depth
- worker utilization
- failure trend by module/provider
