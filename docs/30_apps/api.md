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

- REST endpoints (project/job/config/artifact)
- WebSocket primary channel: `/ws/jobs/{job_id}`
- Optional aggregate channel: `/ws/projects/{project_id}/summary` (list-only summaries)

Key REST endpoints:
- `POST /ingest/probe`: probe URL formats only (no download), for quality picker UI.
- `POST /jobs`: create one job with ingest config snapshot (including optional format IDs).

Ingest config notes:
- Default UX path: send `video_format_id` + `audio_format_id`.
- Advanced path: `ytdlp_format` / `ytdlp_sort`.
- Security policy: do not accept raw `cookie_content` from Web; use `cookie_file_path` or `cookie_secret_ref`.

## Control Semantics

- UI controls (`pause/resume/cancel/delete`) always target a specific `job_id`.
- Re-run creates a new `job_id`; previous jobs remain queryable by snapshot/history.

## Notes

- API 不直接实现算法，算法由 `packages/*` 提供
- WS 仅用于实时刷新；状态真相以 HTTP snapshot 为准（见 `docs/10_system/events-and-websocket.md`）
