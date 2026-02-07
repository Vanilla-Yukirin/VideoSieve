# AGENTS.md

Guidance for coding agents operating in `D:\Github\VideoSieve`.

This repository is currently in a documentation-first rebuild phase.
There is no runnable app scaffold yet (`apps/`, `packages/`, `workers/` are planned in docs only).

## 1) Repository Reality Check

- Current source of truth: `docs/ARCHITECTURE.md`
- Doc index: `docs/README.md`
- Planned stack: FastAPI + Celery + Redis + Next.js + SQLite
- Current state: no `pyproject.toml`, no `package.json`, no CI scripts, no tests

## 2) Rule Files (Cursor/Copilot)

Checked locations:
- `.cursor/rules/` -> not present
- `.cursorrules` -> not present
- `.github/copilot-instructions.md` -> not present

If any of the above are added later, treat them as higher-priority local policy and update this file.

## 3) Build / Lint / Test Commands

Because the code scaffold is not yet created, there are no verified build/lint/test commands today.

Use this status legend:
- VERIFIED: works in current repo
- PLANNED: expected command once scaffold exists

### 3.1 Currently Verified Commands

- `git status` (repo hygiene)
- `git diff` (review changes)

### 3.2 Planned Python Backend Commands (FastAPI/Celery)

Run from repo root unless noted.

- Environment activation (REQUIRED before running Python code/commands):
  - `conda activate VideoSieve`

- Setup env (PLANNED):
  - `python -m venv .venv`
  - `.venv\\Scripts\\activate` (Windows)
  - `pip install -e .[dev]`

- Lint (PLANNED):
  - `ruff check .`

- Format (PLANNED):
  - `ruff format .`

- Type check (PLANNED):
  - `mypy apps packages workers`

- Test all (PLANNED):
  - `pytest`

- Test single file (PLANNED):
  - `pytest tests/unit/test_xxx.py`

- Test single test case (PLANNED, preferred):
  - `pytest tests/unit/test_xxx.py::test_case_name -q`

- Test by keyword (PLANNED):
  - `pytest -k "keyword" -q`

### 3.3 Planned Web Commands (Next.js)

- Install deps (PLANNED): `npm install` (or `pnpm install` if lockfile indicates pnpm)
- Dev server (PLANNED): `npm run dev`
- Build (PLANNED): `npm run build`
- Lint (PLANNED): `npm run lint`
- Test all (PLANNED): `npm test`
- Single test (PLANNED): `npm test -- path/to/test.spec.ts`

### 3.4 Planned Worker/Compose Commands

- Start local services (PLANNED): `docker compose up -d redis`
- Start API (PLANNED): command to be defined in scaffold
- Start worker (PLANNED): command to be defined in scaffold

When scaffold is added, replace PLANNED commands with exact verified commands.

## 4) Coding Style Guidelines

Apply these conventions unless a future local config overrides them.

### 4.1 General

- Prefer small, composable modules with explicit boundaries.
- Keep cross-module contracts in `docs/10_system/*` and code contracts in shared schema modules.
- Do not introduce hidden coupling between apps and providers.
- Avoid premature abstraction; optimize for clarity and testability.

### 4.2 Python Style (backend/workers/packages)

- Target Python 3.11+ semantics.
- Use type hints on all public functions/methods.
- Prefer `pydantic` models or typed dataclasses for structured payloads.
- Use `pathlib.Path` over raw string paths.
- Keep functions focused; extract helpers when >40-60 lines.
- Imports order: stdlib -> third-party -> local; keep grouped and sorted.
- Avoid `from module import *`.
- Naming:
  - modules/files: `snake_case.py`
  - functions/vars: `snake_case`
  - classes: `PascalCase`
  - constants: `UPPER_SNAKE_CASE`
- Error handling:
  - Do not swallow exceptions silently.
  - Raise domain-specific errors with actionable context.
  - Preserve original exception via `raise ... from e` when wrapping.
  - Include `project_id`, `job_id`, and `stage` in logs/errors where relevant.

### 4.3 FastAPI / API Layer

- Keep route handlers thin; delegate business logic to service/modules.
- Validate all request/response payloads with typed models.
- Return consistent error envelopes (`code`, `message`, optional `hint`, `retryable`).
- Keep API side effects explicit and traceable.

### 4.4 Worker / Pipeline Layer

- Implement cooperative interruption at documented safety points.
- Check control flags before/after expensive calls and inside long loops.
- Prefer soft-cancel first; hard terminate only with cleanup logging.
- Emit structured progress/events consistently with contract docs.

### 4.5 Frontend Style (Next.js)

- Use TypeScript strict mode style.
- Component names in `PascalCase`; hooks as `useXxx`.
- Keep side effects isolated in hooks/services.
- Treat HTTP snapshot as source of truth; WS is incremental refresh.
- Avoid embedding protocol literals in UI components; centralize in client layer.

## 5) Naming and Contract Rules

- Distinguish `project` (long-lived container) vs `job` (single run).
- Control commands and event streams are job-scoped by default.
- Persisted artifact paths must follow workspace canonical layout.
- Schema changes require versioning and docs updates.

## 6) Change Management Expectations

When you change behavior:
- Update relevant docs in `docs/10_system/` first (or in same PR).
- Update ADR if architectural decision changes (`docs/adr/`).
- Keep `docs/ARCHITECTURE.md` as high-level overview, not implementation dump.

## 7) Agent Workflow Checklist

Before coding:
- Read `docs/README.md`, `docs/ARCHITECTURE.md`, and relevant `docs/10_system/*`.

While coding:
- Keep diffs focused.
- Add/adjust tests with behavior changes.
- Follow style rules above.

Before finishing:
- Run available lint/tests (or state clearly if not yet scaffolded).
- Summarize assumptions and any PLANNED commands not yet verifiable.

## 8) Temporary Limitation Notice

If a requested command fails because scaffold is missing, do not invent success.
Report clearly: command status = NOT YET AVAILABLE, and point to required scaffold file(s).
