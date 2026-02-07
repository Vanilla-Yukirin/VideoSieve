# State Machine

## 1. Core Objects

- `Project`
- `Job`
- `Stage`

## 2. Job State

`queued -> running -> paused -> running -> succeeded|failed|cancelled`

Rules:
- `pause` only valid while running
- `resume` only valid while paused
- `delete` follows two-phase rule (cancel first)

## 3. Stage State

`pending -> running -> succeeded|failed|skipped`

## 4. Progress Model

- Stage weighted progress + in-stage sub-progress
- Default weights defined in `docs/ARCHITECTURE.md`

## 5. Idempotency

- Repeated control commands must not corrupt state
- State transition violations must return explicit error code

## 6. Command x JobState Matrix

Legend: `ALLOW` / `NOOP` / `ERROR`

| JobState | pause | resume | cancel | delete |
|---|---|---|---|---|
| `queued` | `NOOP` | `ERROR` | `ALLOW` | `ALLOW` (internally cancel->cleanup) |
| `running` | `ALLOW` | `NOOP` | `ALLOW` | `ALLOW` (internally cancel->cleanup) |
| `paused` | `NOOP` | `ALLOW` | `ALLOW` | `ALLOW` (internally cancel->cleanup) |
| `succeeded` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |
| `failed` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |
| `cancelled` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |

## 7. Error Codes for Invalid/Conflict Transitions

- `INVALID_STATE_TRANSITION`: command not allowed in current state
- `ALREADY_IN_TARGET_STATE`: idempotent no-op acknowledged
- `JOB_NOT_ACTIVE`: command requires active job but job already terminal
- `DELETE_PENDING_CLEANUP`: delete accepted but cleanup still in progress
- `CONTROL_CONFLICT`: concurrent control commands conflict on same job
