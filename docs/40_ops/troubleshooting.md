# Troubleshooting

## Common Issues

### Download fails
- check source visibility/cookie auth
- retry with alternative format

### ASR timeout
- verify provider status and network
- resume from checkpoint

### Too few keyframes
- lower stability threshold
- enable fallback sampling

### Delete hangs
- verify cancel phase completion before cleanup

### UI not updating / WS disconnected
- verify WS connection health and the outer trusted access path
- verify API can read SQLite `job_events` after the client's last `event_id`
- reconnect with the last continuous cursor; if expired, accept `cursor_reset` and rebuild from WS snapshot

### Missing log lines
- compare the client cursor with the database event retention boundary
- reconcile from persisted events and `workspaces/.../logs/worker.log`; do not invent missing continuity

### Job stuck in running / interrupted
- check worker heartbeat, attempt owner and OS service state
- check managed child processes before any recovery
- heartbeat timeout may mark `interrupted`, but never start a replacement attempt automatically
- recover only after confirming the old worker/process tree stopped and validating reusable artifacts

## Incident Data to Collect

- project_id/job_id
- stage and failure code
- recent events and worker logs
- WS snapshot, `state_version`, last continuous `event_id` and cursor reset reason
