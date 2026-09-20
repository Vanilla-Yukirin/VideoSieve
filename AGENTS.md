# Agent guidance for VideoSieve

## Repository reality (checked 2026-09-20)

- This is an implemented single-host application with incomplete real-provider acceptance.
  API, Web, business packages, an independent worker, tests and lockfiles exist.
- FastAPI only persists queued jobs. `workers/single_host.py` claims them from SQLite;
  `workers/runtime.py` is the thin execution adapter. Celery and Redis are not used.
- SQLite persists queue ownership, attempts, progress, control versions and cursor events.
  `InMemoryEventBus` is an explicit test/embedding adapter, never the default runtime bus.
- Production ASR is unconfigured by default and uses external adapters. CapsWriter's
  upstream WebSocket protocol is implemented and authentication is optional.
  Frame-summary and overall-summary failures are explicit;
  test doubles live under `tests/`. Final deliverables publish a hashed
  readiness manifest only after the complete generation is ready.
- Target scope confirmed by the user: one computer/server, one or a few users. The
  SQLite plus separate Python worker architecture is implemented; real video/provider
  output and target-host service supervision still require acceptance evidence.
- `.cursor/rules/`, `.cursorrules`, and `.github/copilot-instructions.md` were absent
  at this check. Read applicable rule files if added later.

## Read before changing behavior

- `docs/README.md`: documentation index.
- `docs/ARCHITECTURE.md`: existing architecture baseline, including unimplemented plans.
- `docs/00_vision/rebuild-plan.md`: current findings and proposed single-host rebuild.
- Relevant `docs/10_system/*` contracts and `docs/20_modules/*` module documents.

Distinguish observed implementation, proposed design and verified runtime behavior.
Update contracts and ADRs with architectural changes; a proposal is not shipped code.

## Environment and commands

Use `uv` and `.venv`; conda activation is not required. `.python-version` selects
Python 3.12; `pyproject.toml` allows Python >=3.11. Follow the checked-in pin for
local setup. Check an existing environment before recreating it.

These commands are the current repository entrypoints; report the result of each run:

```powershell
uv sync --extra dev
uv run pytest
uv run pytest tests/unit/test_infra_sqlite_repository.py -q
uv run ruff check .
uv run mypy apps packages workers
npm --prefix apps/web ci
npm --prefix apps/web run dev
npm --prefix apps/web run build
npm --prefix apps/web test -- --runInBand
```

Bare `uv run pytest` discovers unit, contract and integration Python suites. The harness
also runs frontend and static checks. The base install contains no FunASR, PyTorch,
Torchaudio or Transformers runtime. See `how_to_run.md` for external ASR configuration. Start
the independent worker with `uv run python -m workers.single_host --data-dir runtime/api`.
Do not prescribe Redis/Celery startup.

## Implementation conventions

- Confirm cwd, branch and Git status before edits; preserve unrelated changes.
- `apps/` owns entrypoints, `packages/` reusable logic, `workers/` execution setup.
  Keep routes and worker entrypoints thin; avoid hidden cross-module coupling.
- Use typed contracts, public Python type hints and `pathlib.Path`. Prefer focused
  modules and explicit provider interfaces; no generic workflow framework is needed.
- Python: snake_case functions/modules, PascalCase classes, UPPER_SNAKE_CASE constants;
  imports ordered stdlib, third-party, local. TypeScript: strict types, PascalCase
  components, `useXxx` hooks, protocol values centralized in the client layer.
- Distinguish long-lived `project` from one execution `job`. Control/events are
  job-scoped. Keep schema versions and canonical workspace paths consistent.
- Errors retain actionable context (`project_id`, `job_id`, `stage`) and use the
  `code/message/hint/retryable` envelope where applicable. Preserve exception causes.
- New or changed production paths must not turn missing configuration, provider
  failures or malformed responses into successful mock content. Test doubles belong
  in tests.
- Preserve raw transcripts and evidence separately from model-written outputs.
- Interruption is cooperative: check before/after expensive operations and within
  long loops. Requested pause/cancel and confirmed stopped states are distinct.
- Job WebSocket snapshots are authoritative; persisted cursor events incrementally refresh the UI.
- Keep secrets out of Git, logs, snapshots and generated deliverables.

## Verification and completion

- Run checks relevant to changed behavior; report failures and unverified steps.
- For model integration, file existence and mock success are insufficient: verify
  real input, provider output, failure reporting and saved artifacts.
- For scheduling, verify restart recovery, task ownership and actual pause/cancel
  behavior, not only state labels.
- Documentation-only changes need consistency/link checks and `git diff --check`;
  they do not establish that the application or model services work.
