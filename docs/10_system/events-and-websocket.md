# Events and WebSocket Protocol

## 1. Goals

- Real-time logs and progress
- Bidirectional control: `pause/resume/cancel/delete`

## 2. Event Model (Server -> Client)

- `log`: `{project_id, job_id, ts, level, message}`
- `progress`: `{project_id, job_id, stage, pct, eta?}`
- `stage_changed`: `{project_id, job_id, from, to}`
- `artifact_ready`: `{project_id, job_id, artifact_type, path_or_url}`
- `error`: `{project_id, job_id, stage, code, message, hint?}`
- `control_ack`: `{project_id, job_id, command, accepted, reason?}`

## 3. Control Commands (Client -> Server)

### `pause`
- Semantics: cooperative pause at safety points

### `resume`
- Semantics: continue from paused checkpoint

### `cancel`
- Semantics: soft cancel first, ensure cleanup for child resources

### `delete`
- Semantics: two-phase, cancel then cleanup workspace/DB

## 4. Safety Points

- Stage boundary checks
- Long-running sub-step checks (poll flag periodically)

## 5. Delivery Rules

- Event ordering by server timestamp within one job
- Reconnect must fetch latest job snapshot via HTTP (`status`, `stage`, latest progress/log cursor)
- Recent event replay is optional and only available when event bus supports it (Redis Streams or persisted ring buffer)
- In Redis Pub/Sub mode, events are best-effort; UI state must converge to snapshot as source of truth
