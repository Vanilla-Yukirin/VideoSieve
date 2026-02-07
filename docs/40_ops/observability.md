# Observability

## Minimum Signals

- project total duration/final state
- stage duration/retry/failure code
- ASR confidence and hotword hit rate
- keyframe count/duplication/diff curve
- OCR confidence distribution

## Logs

- structured logs with `project_id`, `job_id`, `stage`
- error logs include `code`, `hint`, `retryable`

## UI Rebuild Requirement

- UI state must be reconstructable from HTTP snapshot + artifact index without relying on WS replay.
- WS accelerates refresh only; snapshot remains source of truth.
- Snapshot minimum fields: `job status`, `current stage`, `progress`, `latest logs cursor/window`, `artifact list`.

## Dashboards (Future)

- queue depth
- worker utilization
- failure trend by module/provider
