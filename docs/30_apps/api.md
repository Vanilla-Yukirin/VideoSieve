# App: api

状态：SQLite 队列与 job WebSocket 控制面已实现。REST 路由承担认证、设置、项目与
任务创建、上传和下载；这就是当前接口边界，不再把它描述成等待全量迁移到 WS 的旧接口。
标为 `implemented` 只表示代码路径存在，不代替运行验收。

## Purpose

提供认证、受限 HTTP 文件接口与 WebSocket 业务网关。API 创建任务时只持久化配置快照
和 queued 记录，不在 API 进程内执行媒体 pipeline。

## Domain Axis (Project vs Job)

- `Project` 是长期实体（视频来源与历史运行容器）。
- `Job` 是一次运行（配置快照、状态机、事件流、产物集合）。
- 控制命令与实时事件以 `job_id` 为主轴，避免重跑时语义歧义。

## Responsibilities

- validate commands and persist project/job/config records
- serve authoritative snapshots and cursor events over WebSocket
- expose uploads, media/artifact downloads and health checks over HTTP
- read SQLite events and push them to authenticated WS subscriptions

## Interfaces

Current runtime exposes REST endpoints for auth/settings/project/job/config/artifact and a
job WebSocket channel. The implemented split is:

- HTTP: authentication, settings, project/job CRUD, upload, media/artifact download and health;
- WebSocket: one job's authoritative snapshot, control commands and cursor events;
- large binary files never travel inside WebSocket messages.

The `/ws/jobs/{job_id}` route and command registry are versioned with
`docs/10_system/events-and-websocket.md`.

Status markers used below:
- `implemented`: code path observed in the rebuild audit; runtime/E2E validation is separate.
- `planned`: documented target, not in current runtime.

Key REST endpoints:
- `implemented` `GET /public/access-flags`: public bootstrap hint (`guest_mode_enabled` only).
- `implemented` `GET /auth/bootstrap-status`, `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- `implemented` `GET /settings/system`, `PATCH /settings/system`.
- `implemented` `GET /projects`: list SQLite-backed projects in stable newest-first creation order.
- `implemented` `GET /guest/cooldown`: global cooldown state (`active`, `remaining_seconds`, `cooldown_seconds`).
- `implemented` `POST /ingest/probe`: URL format probe only (no download).
- `implemented` `POST /jobs`: create a job snapshot and persist a queued job in the audited REST path.
- `implemented` `POST /projects/{project_id}/jobs/upload`: stage an upload inside the project's
  workspace, then create a job; rejected job creation removes the staged file.
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
- `implemented` `GET /jobs/{job_id}/artifacts` only returns final deliverables whose readiness
  manifest matches project/job identity and whose file size/SHA-256 still matches.
- `implemented` constrained download routes expose individual artifacts and the keyframe archive.

## Control Semantics

- UI controls (`pause/resume/cancel/delete`) always target a specific `job_id`.
- Re-run creates a new `job_id`; previous jobs remain queryable by snapshot/history.
- accepted requests are persisted separately from worker-confirmed applied state.
- API cannot report paused/cancelled merely because it wrote a control flag.
- heartbeat timeout yields `interrupted`; API cannot auto-dispatch a replacement attempt.

## Notes

- API 不直接实现算法，算法由 `packages/*` 提供
- job state truth is a WebSocket snapshot backed by SQLite; increments use persisted event cursor
- process-local notifications may wake the gateway but are never the recovery source
- `/healthz` currently proves API liveness only; DB/workspace/worker readiness is not yet implemented.
- `APP_SECRET_KEY` is a startup precondition for API runtime; missing key fails fast at startup.
- `implemented` API error semantics in runtime:
  - `auth_required`, `invalid_credentials`, `bootstrap_required`
  - `guest_cookie_key_required`, `guest_cooldown_active`
  - `not_found`, `validation_error`, `config_error`, `internal_error`
