# Deployment

## Runtime Stack

- API container
- Worker container
- Web container
- Redis service
- SQLite volume (or future Postgres)

## Baseline

- use `docker/` as canonical deployment source
- separate env for api/web/worker

Status markers:
- `implemented`: active runtime behavior.
- `planned`: target behavior for future deployment profile.

## API Env (Minimum Required)

- `implemented` required: `APP_SECRET_KEY`
- `implemented` optional with defaults: `ENABLE_GUEST_MODE`, `GUEST_ALLOW_COOKIE_INPUT`, `GUEST_JOB_COOLDOWN_SECONDS`, `VIDEOSIEVE_EVENTBUS_STUB_MODE`
- `implemented` conditionally required: `GUEST_COOKIE_KEY` when guest cookie input is enabled by persisted settings
- `implemented` VLM runtime keys: `QWEN_API_KEY`, `QWEN_BASE_URL`, `VLM_MODEL`, `VLM_TIMEOUT_SECONDS`

Default policy:
- `implemented` guest mode defaults to disabled when `ENABLE_GUEST_MODE` is not set.

## Web Env (Minimum Required)

- `implemented` `NEXT_PUBLIC_API_ORIGIN` (for API/WS target origin in browser runtime)

Public vs secret rule:
- Any `NEXT_PUBLIC_*` variable is exposed to browser clients.
- Never place secrets (for example `APP_SECRET_KEY`, provider tokens, private cookie material) in `NEXT_PUBLIC_*` keys.

Startup guardrails:
- `implemented` API startup fails fast when `APP_SECRET_KEY` is missing/blank.
- `implemented` API startup rejects illegal guest-cookie configuration when persisted setting requires `GUEST_COOKIE_KEY` but env is empty.

## Container and Storage Constraints (MVP)

- API and worker must mount the same workspace volume path (read/write compatible).
- If worker writes artifacts under workspace, API must read from the same mounted root.
- SQLite is acceptable for MVP, but write-path ownership must be explicit to avoid lock contention.

Recommended MVP policy:
- API is the primary DB writer for project/job/status updates.
- Worker reports status/events through API or serialized channel; avoid uncontrolled concurrent SQLite writes.
- planned: after migration to Postgres, API and worker may both write with normal transaction control.

## Checklist

- health checks configured
- persistent workspace volume mounted
- secrets injected via env or secret manager
- API/worker workspace mount path verified identical
- SQLite write ownership policy documented and tested
