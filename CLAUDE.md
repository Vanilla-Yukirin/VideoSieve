# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Current status and conventions: read `AGENTS.md`. The single-host SQLite worker rebuild is
implemented; `docs/00_vision/rebuild-plan.md` records the migration and remaining real-model
acceptance work. Commands below are entrypoints, not evidence until actually run.
`.python-version` currently pins 3.12.

## Commands

### Python (via uv)

```bash
uv run pytest                          # unit + contract + integration Python tests
uv run pytest tests/unit/test_foo.py::test_bar  # single test
uv run ruff check .                    # lint
uv run ruff check . --fix              # lint + auto-fix
uv run mypy apps packages workers      # type check
```

### Frontend

```bash
npm --prefix apps/web run dev          # dev server (http://localhost:3000)
npm --prefix apps/web run lint         # declared; dependency compatibility needs verification
npx --prefix apps/web tsc --noEmit    # TypeScript check
```

### Running the stack locally

```bash
# Terminal 1 — backend
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000

# Terminal 2 — independent worker
uv run python -m workers.single_host --data-dir runtime/api

# Terminal 3 — frontend
npm --prefix apps/web run dev
```

Copy `.env.example` → `.env.local`. Minimum required env vars: `APP_SECRET_KEY`, `NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000`.

ASR is external and unconfigured by default. Select `capswriter` in system settings or seed
`VIDEOSIEVE_ASR_PROVIDER=capswriter` and `VIDEOSIEVE_ASR_ENDPOINT=ws://host:6016` before
the first API start. The adapter uses CapsWriter's official WebSocket protocol. The optional
`CAPSWRITER_TOKEN` stays in the worker environment. The base install contains no ASR model
runtime and never downloads a speech model.

For VLM (frame summaries): set `QWEN_API_KEY` in `.env.local`. Base URL / model / prompts / concurrency are stored in SQLite and editable via `/settings/system`.

## Architecture

### Layer boundaries

```
apps/api      → FastAPI HTTP + WebSocket. Owns auth, durable queue/control/event R/W.
apps/web      → Next.js. Communicates with api only via NEXT_PUBLIC_API_ORIGIN.
packages/*    → Reusable business logic and provider adapters; some adapters perform HTTP/DB access.
workers/      → Independent SQLite queue process plus a thin runtime adapter.
infra/        → Concrete adapters: SQLiteJobRepository, SQLiteEventBus, FileSystemWorkspaceStore.
```

`infra/` above means `packages/infra`. Keep dependencies directed from entrypoints to
business modules and provider interfaces. Business modules must not depend on apps
or workers; infrastructure adapters must not depend on business modules.

### Pipeline stages (fixed order)

`ingest → hotwords → asr → keyframes → frame_summary → fusion → deliverables`

Orchestrated by `packages/pipeline/orchestrator.py`. Each stage writes artifacts to the workspace,
persists state/progress and publishes cursor events: **worker → SQLite → WebSocket → frontend**.
`InMemoryEventBus` exists only for explicit tests and embedding.

Control commands enter through **frontend → `/ws/jobs/{id}` → API → SQLite**. The worker
acknowledges a versioned request at a safety point. Queue claims and worker writes are fenced by
worker identity and attempt. Interrupted jobs require explicit recovery; no Redis flags exist.

### Workspace layout (per job)

```
workspaces/{project_id}/jobs/{job_id}/
  asr/transcript.jsonl          # {segment_id, start, end, text, lang, conf}
  frames/
    keyframes.jsonl             # {frame_id, ts, path, hash, score, reason}
    images/slide_000001.jpg     # frame_id "frame_000001" → image "slide_000001.jpg"
  frame_summary/frame_summary.jsonl  # {frame_id, description_text, lang, provider}
  fusion/timeline.json          # merged timeline
  outputs/
    clean_transcript.md
    illustrated_notes.md
    summary.json                # only when model summary is enabled
    deliverables.ready.json     # published last; hashes the ready generation
```

### Settings (SQLite key-value store)

Mutable runtime settings live in SQLite via `get_setting`/`set_setting` in `apps/api/service.py`.
Creating a job freezes non-secret VLM and summary configuration into its immutable snapshot;
the worker reads that snapshot. When adding a setting, update the API models, snapshot builder,
pipeline reader and Web types together.

### Frontend data fetching

The job detail page uses `/ws/jobs/{id}` for snapshot-first state, cursor replay, progress and
control acknowledgement. HTTP remains for project/job creation, settings, upload, media playback
and artifact download. The UI must ignore stale state versions and duplicate event cursors.

### Key files

| File | Purpose |
|------|---------|
| `apps/api/main.py` | FastAPI app factory, all route registrations |
| `apps/api/service.py` | All business logic callable from REST/WS handlers |
| `apps/api/models.py` | Pydantic request/response models |
| `packages/pipeline/orchestrator.py` | Stage dispatch loop, reads immutable job config |
| `workers/single_host.py` | SQLite claim/heartbeat loop and process lock |
| `packages/frame_summary/service.py` | Concurrent VLM calls with RPM rate limiter |
| `apps/web/components/DeliverablesTabs.tsx` | 3-tab results preview (raw / polished / summary) |
| `apps/web/lib/i18n/messages.ts` | All UI strings; add `MessageKey` union here first |
