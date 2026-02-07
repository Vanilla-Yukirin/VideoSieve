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

## Container and Storage Constraints (MVP)

- API and worker must mount the same workspace volume path (read/write compatible).
- If worker writes artifacts under workspace, API must read from the same mounted root.
- SQLite is acceptable for MVP, but write-path ownership must be explicit to avoid lock contention.

Recommended MVP policy:
- API is the primary DB writer for project/job/status updates.
- Worker reports status/events through API or serialized channel; avoid uncontrolled concurrent SQLite writes.
- After migration to Postgres, API and worker may both write with normal transaction control.

## Checklist

- health checks configured
- persistent workspace volume mounted
- secrets injected via env or secret manager
- API/worker workspace mount path verified identical
- SQLite write ownership policy documented and tested
