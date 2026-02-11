# App: api

## Purpose

提供 HTTP API 与 WebSocket 网关，负责项目控制面。

## Domain Axis (Project vs Job)

- `Project` 是长期实体（视频来源与历史运行容器）。
- `Job` 是一次运行（配置快照、状态机、事件流、产物集合）。
- 控制命令与实时事件以 `job_id` 为主轴，避免重跑时语义歧义。

## Responsibilities

- create/list project and job
- expose artifacts and status
- validate config and create job snapshot
- subscribe event bus and push WS events

## Interfaces

- REST endpoints (auth/settings/project/job/config/artifact)
- WebSocket primary channel: `/ws/jobs/{job_id}`
- Optional aggregate channel: `/ws/projects/{project_id}/summary` (list-only summaries)

Status markers used below:
- `implemented`: available in current API runtime.
- `planned`: documented target, not in current runtime.

Key REST endpoints:
- `implemented` `GET /public/access-flags`: public bootstrap hint (`guest_mode_enabled` only).
- `implemented` `GET /auth/bootstrap-status`, `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- `implemented` `GET /settings/system`, `PATCH /settings/system`.
- `implemented` `GET /guest/cooldown`: global cooldown state (`active`, `remaining_seconds`, `cooldown_seconds`).
- `implemented` `POST /ingest/probe`: URL format probe only (no download).
- `implemented` `POST /jobs`: create job snapshot and enqueue dispatch.
- `implemented` `GET /jobs/{job_id}/source-video`: returns workspace `media/source.mp4` for player/download.
- `implemented` Cookie Vault: `POST /me/cookies`, `GET /me/cookies`, `PATCH /me/cookies/{cookie_id}`, `DELETE /me/cookies/{cookie_id}`.
- `implemented` `POST /me/cookies/{cookie_id}/validate`: validate cookie against a concrete video page URL.
- `planned` `GET /operation-logs`: query operation logs via API endpoint (current runtime writes logs to storage only).

Ingest config notes:
- Create-job path is format-id only (`analysis_asset` + `quality_asset` with `video_format_id`/`audio_format_id`).
- Probe path no longer accepts `ytdlp_sort` from client payload.
- Create-job accepts `cookie_id` (preferred) and keeps `cookie_file_path` as migration fallback.
- Security policy: do not accept raw `cookie_content` from Web create-job payloads.

Cookie validate notes:
- `implemented` `source_url` is required and must point to a concrete video page.
- `implemented` homepage/root URLs (for example `https://www.bilibili.com` or `https://bilibili.com/`) are rejected to avoid false-negative validation.

Artifact exposure notes:
- `implemented` `GET /jobs/{job_id}/artifacts` returns artifact metadata list (`path`, `size_bytes`).
- `planned` generic per-artifact download routes and signed URLs are documented in artifact realtime expansion plan.

## Control Semantics

- UI controls (`pause/resume/cancel/delete`) always target a specific `job_id`.
- Re-run creates a new `job_id`; previous jobs remain queryable by snapshot/history.

## Notes

- API 不直接实现算法，算法由 `packages/*` 提供
- WS 仅用于实时刷新；状态真相以 HTTP snapshot 为准（见 `docs/10_system/events-and-websocket.md`）
- `APP_SECRET_KEY` is a startup precondition for API runtime; missing key fails fast at startup.
- `implemented` API error semantics in runtime:
  - `auth_required`, `invalid_credentials`, `bootstrap_required`
  - `guest_cookie_key_required`, `guest_cooldown_active`
  - `not_found`, `validation_error`, `config_error`, `internal_error`
