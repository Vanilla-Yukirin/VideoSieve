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
- verify WS connection health and auth
- verify Redis event bus health
- fall back to HTTP snapshot refresh; treat snapshot as source of truth

### Missing log lines
- Pub/Sub mode may drop transient events during reconnect
- reconcile using HTTP snapshot + `workspaces/.../logs/worker.log`

## Incident Data to Collect

- project_id/job_id
- stage and failure code
- recent events and worker logs
- snapshot response payload at failure time
