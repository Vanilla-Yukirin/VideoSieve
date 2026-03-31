# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python (via uv)

```bash
uv run pytest                          # all unit tests
uv run pytest tests/unit/test_foo.py::test_bar  # single test
uv run ruff check .                    # lint
uv run ruff check . --fix              # lint + auto-fix
uv run mypy apps packages workers      # type check
```

### Frontend

```bash
npm --prefix apps/web run dev          # dev server (http://localhost:3000)
npm --prefix apps/web run lint         # ESLint
npx --prefix apps/web tsc --noEmit    # TypeScript check
```

### Running the stack locally

```bash
# Terminal 1 — backend
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
npm --prefix apps/web run dev
```

Copy `.env.example` → `.env.local`. Minimum required env vars: `APP_SECRET_KEY`, `NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000`.

For local ASR: `uv sync --extra dev --extra asr_local` and set `VIDEOSIEVE_ASR_PROVIDER=funasr_local`.

For VLM (frame summaries): set `QWEN_API_KEY` in `.env.local`. Base URL / model / prompts / concurrency are stored in SQLite and editable via `/settings/system`.

## Architecture

### Layer boundaries

```
apps/api      → FastAPI HTTP + WebSocket. Owns auth, SQLite R/W, job dispatch via Celery.
apps/web      → Next.js. Communicates with api only via NEXT_PUBLIC_API_ORIGIN.
packages/*    → Pure business logic modules. No direct DB or HTTP; consume interfaces only.
workers/      → Thin Celery adapter. Delegates entirely to packages/pipeline/orchestrator.py.
infra/        → Concrete adapters: SQLiteJobRepository, FileSystemWorkspaceStore, RedisEventBus.
```

`apps/` can import from `packages/` and `infra/`. `packages/` cannot import from `apps/` or `workers/`. `infra/` cannot import from `packages/` business logic.

### Pipeline stages (fixed order)

`ingest → hotwords → asr → keyframes → frame_summary → fusion → deliverables`

Orchestrated by `packages/pipeline/orchestrator.py`. Each stage writes artifacts to the workspace, then publishes Redis events that flow: **worker → Redis → API → WebSocket → frontend**.

Control commands (pause/resume/cancel) travel in reverse: **frontend → POST /jobs/{id}/control/{cmd} → API → Redis flag → worker polls at stage boundaries**.

### Workspace layout (per job)

```
workspaces/{project_id}/jobs/{job_id}/
  asr/transcript.jsonl          # {segment_id, start, end, text, lang, conf}
  frames/
    keyframes.jsonl             # {frame_id, ts, path, hash, score, reason}
    images/slide_000001.jpg     # frame_id "frame_000001" → image "slide_000001.jpg"
  frame_summary/frame_summary.jsonl  # {frame_id, description_text, lang, provider}
  fusion/timeline.json          # merged timeline
  outputs/                      # deliverables (md, json, html)
```

### Settings (SQLite key-value store)

Mutable runtime settings live in SQLite via `get_setting`/`set_setting` in `apps/api/service.py`. Constants like `SETTING_VLM_BASE_URL` are defined there and mirrored in `packages/pipeline/orchestrator.py` as `_SETTING_*` strings. When adding a new setting, update both files, `apps/api/models.py`, and `apps/web/lib/api/types.ts`.

The pattern for reading a setting in the orchestrator is `_read_vlm_str`/`_read_vlm_int` — these read from the DB without writing back (unlike the API-side helpers which lazy-init on first read).

### Frontend data fetching

The job detail page polls job status; `DeliverablesTabs` fetches artifact JSONL files directly via `/api/jobs/{id}/artifacts/download/{path}`. Frame summaries are polled every 4 s while the job is running (to pick up streaming writes from the concurrent VLM stage).

### Key files

| File | Purpose |
|------|---------|
| `apps/api/main.py` | FastAPI app factory, all route registrations |
| `apps/api/service.py` | All business logic callable from REST/WS handlers |
| `apps/api/models.py` | Pydantic request/response models |
| `packages/pipeline/orchestrator.py` | Stage dispatch loop, reads settings from DB |
| `packages/frame_summary/service.py` | Concurrent VLM calls with RPM rate limiter |
| `apps/web/components/DeliverablesTabs.tsx` | 3-tab results preview (raw / polished / summary) |
| `apps/web/lib/i18n/messages.ts` | All UI strings; add `MessageKey` union here first |
