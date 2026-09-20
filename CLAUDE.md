# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Current status and conventions: read `AGENTS.md`. The proposed single-host rebuild is
in `docs/00_vision/rebuild-plan.md`; it is not implemented. Commands below are declared
entrypoints, not evidence of passing checks. `.python-version` currently pins 3.12.

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
npm --prefix apps/web run lint         # declared; dependency compatibility needs verification
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

For local ASR: `uv sync --extra dev` and set `VIDEOSIEVE_ASR_PROVIDER=funasr_local`.
FunASR/PyTorch are currently main dependencies; `asr_local` is an empty extra.
Models load on first transcription, not during API startup.

For VLM (frame summaries): set `QWEN_API_KEY` in `.env.local`. Base URL / model / prompts / concurrency are stored in SQLite and editable via `/settings/system`.

## Architecture

### Layer boundaries

```
apps/api      → FastAPI HTTP + WebSocket. Owns auth, SQLite R/W, job dispatch via daemon threads.
apps/web      → Next.js. Communicates with api only via NEXT_PUBLIC_API_ORIGIN.
packages/*    → Reusable business logic and provider adapters; some adapters perform HTTP/DB access.
workers/      → Plain Python adapter. Delegates to packages/pipeline/orchestrator.py.
infra/        → Concrete adapters: SQLiteJobRepository, FileSystemWorkspaceStore, RedisEventBus.
```

`infra/` above means `packages/infra`. Keep dependencies directed from entrypoints to
business modules and provider interfaces. Business modules must not depend on apps
or workers; infrastructure adapters must not depend on business modules.

### Pipeline stages (fixed order)

`ingest → hotwords → asr → keyframes → frame_summary → fusion → deliverables`

Orchestrated by `packages/pipeline/orchestrator.py`. Each stage writes artifacts to the workspace,
then publishes in-memory events: **API task thread → event bus → WebSocket → frontend**.
`RedisEventBus` has no live Redis implementation.

Control commands enter through **frontend → POST /jobs/{id}/control/{cmd} → API**.
The API changes SQLite state; the orchestrator also has instance-local control sets.
Pause/resume execution semantics need repair and real integration checks; no Redis flags exist.
See the rebuild plan for durable control and recovery requirements.

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
