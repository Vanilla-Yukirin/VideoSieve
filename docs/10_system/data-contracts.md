# Data Contracts

This document defines cross-module contract semantics for VideoSieve.
It is contract-oriented (meaning and boundaries), not implementation-oriented (SDK/ORM/runtime details).

## 1. Contract Principles

- Heavy data stays on workspace storage; persistence stores indexes, state snapshots, and references.
- All contracts include `schema_version`.
- Field evolution is additive-first; breaking changes require migration notes.
- Naming remains stable across modules: `project` (long-lived container) vs `job` (single run).
- Contract descriptions use explicit `required` / `optional` labels.

`schema_version` placement:
- JSON object files (for example `timeline.json`): top-level field.
- JSONL stream files (for example `transcript.jsonl`): each line object includes `schema_version`.

## 2. Canonical Domain Objects

### 2.1 Project [已有代码结构；运行验收未由本文证明]

- Purpose: long-lived container for one source and its run history.
- Required:
  - `schema_version`
  - `project_id`
  - `source_type`
  - `source_ref`
  - `title`
  - `status`
  - `created_at`

Example:
```json
{
  "schema_version": "1.0",
  "project_id": "p_20260208_001",
  "source_type": "bilibili_url",
  "source_ref": "https://www.bilibili.com/video/BV...",
  "title": "Linear Algebra Lecture 01",
  "status": "running",
  "created_at": "2026-02-08T10:00:00Z"
}
```

### 2.2 Job [当前基础已存在；目标字段待迁移]

- Purpose: one execution run bound to a project.
- Required:
  - `schema_version`
  - `job_id`
  - `project_id`
  - `config_snapshot_path`
  - `execution_state`
  - `requested_action`
  - `state_version`
- Optional:
  - `started_at`
  - `finished_at`

Example:
```json
{
  "schema_version": "1.0",
  "job_id": "j_20260208_001",
  "project_id": "p_20260208_001",
  "config_snapshot_path": "workspaces/p_20260208_001/jobs/j_20260208_001/meta/config.snapshot.json",
  "execution_state": "running",
  "requested_action": "pause_requested",
  "state_version": 27,
  "started_at": "2026-02-08T10:00:05Z",
  "finished_at": null
}
```

Current code still exposes a legacy `status` shape in places. It must be migrated atomically with
the state-machine and WebSocket contracts; documentation does not make the target fields available.

### 2.3 JobAttempt [目标契约（target）]

- Required: `attempt_id`, `job_id`, `worker_id`, `status`, `started_at`, `heartbeat_at`
- Optional: `finished_at`, `end_reason`, `resume_from`, `parent_attempt_id`
- A heartbeat timeout may set the attempt/job to interrupted, but cannot create a replacement attempt.

### 2.4 ControlRequest [目标契约（target）]

- Required: `request_id`, `job_id`, `command`, `phase`, `requested_at`
- Optional: `applied_at`, `code`, `message`, `actor_id`
- `phase` is `accepted|applied|rejected|failed`; accepted never proves computation stopped.

### 2.5 StageState [已实现基础；恢复字段待迁移]

- Purpose: per-stage state snapshot under a job.
- Required:
  - `schema_version`
  - `project_id`
  - `job_id`
  - `stage`
  - `status`
  - `updated_at`
- Optional:
  - `pct` (0-100)

### 2.6 Snapshot and Event Baseline [目标契约（target）]

- `snapshot`: point-in-time state record, delivered through WebSocket after session establishment.
- `event`: SQLite-persisted append record with a monotonically increasing `event_id` cursor.
- Snapshot is authoritative for current state; retained events restore incremental history.
- Reconnect uses `after_event_id`; an expired or discontinuous cursor requires explicit reset.

## 3. Media and Processing Artifacts

### 3.1 TranscriptSegment (`asr/transcript.jsonl`) [已有代码结构]

- Required: `schema_version`, `segment_id`, `start`, `end`, `text`, `lang`, `conf`

Example JSONL line:
```json
{"schema_version":"1.0","segment_id":"seg_00001","start":0.2,"end":4.8,"text":"今天我们来讲线性变换。","lang":"zh","conf":0.93}
```

### 3.2 Keyframe (`frames/keyframes.jsonl`) [已有代码结构]

- Required: `schema_version`, `frame_id`, `ts`, `path`, `hash`, `score`, `reason`

Example JSONL line:
```json
{"schema_version":"1.0","frame_id":"frame_00012","ts":126.4,"path":"workspaces/p_20260208_001/frames/images/slide_000012.jpg","hash":"a91f...","score":0.82,"reason":"stable"}
```

### 3.3 FrameSummary (`frame_summary/frame_summary.jsonl`) [已有代码结构]

- Required: `schema_version`, `frame_id`, `lang`, `provider`, `description_text`

Example JSONL line:
```json
{"schema_version":"1.1","frame_id":"frame_00012","lang":"zh","provider":"qwen_frame_summary","description_text":"画面上半部分是标题“特征值与特征向量”，下半部分是公式推导说明。"}
```

### 3.4 Timeline (`fusion/timeline.json`) [已有代码结构]

- Required:
  - top level: `schema_version`, `project_id`, `job_id`, `chunks[]`
  - per chunk: `chunk_id`, `start`, `end`, `text`
- Optional per chunk:
  - `transcript_refs[]`, `frame_refs[]`, `frame_summary_refs[]`

### 3.5 ArtifactDescriptor [规划中（planned）]

- Purpose: unified description for produced artifacts across APIs/events/UI.
- Required:
  - `project_id`
  - `job_id`
  - `artifact_type` (for example `clean_transcript`, `illustrated_notes`, `summary`, `export_html`)
  - `path_or_url`
  - `snapshot_at`
- Optional:
  - `size_bytes`
  - `mime_type`
  - `checksum`

### 3.6 Artifact realtime semantics [规划中（planned）]

- `artifact_ready` is an event signal only; durability is confirmed by artifact snapshot/read API.
- Repeated `artifact_ready` for the same artifact is idempotent and acceptable.
- Client/UI should converge to latest snapshot if event loss occurs.

## 4. Event Envelope and Error Envelope

### 4.1 EventEnvelope [目标契约（target）]

- Required:
  - `schema_version`
  - `event_id`
  - `event_type`
  - `project_id`
  - `job_id`
  - `state_version`
  - `ts`
  - `payload`
- Optional:
  - `request_id` for command-related events

Known `event_type` values:
- `log`
- `progress`
- `stage_changed`
- `job_state_changed`
- `error`
- `control_ack`
- `artifact_ready`
- `artifact_removed`

Connection-level messages include `snapshot` and `cursor_reset`; they do not need a new persisted
event row. Ordering and deduplication use `event_id`, not timestamps.

### 4.2 ErrorEnvelope [规划中（planned）]

- Purpose: unified error payload contract for HTTP responses, event payloads, and audit records.
- Required:
  - `code`
  - `message`
- Optional:
  - `hint`
  - `retryable`
  - `project_id`
  - `job_id`
  - `stage`

Recommended shape:
```json
{
  "code": "INVALID_STATE_TRANSITION",
  "message": "resume is not allowed when job status is queued",
  "hint": "pause/resume only apply to running/paused jobs",
  "retryable": false,
  "project_id": "p_20260208_001",
  "job_id": "j_20260208_001",
  "stage": "asr"
}
```

## 5. Error Code Registry (Contract-Level)

### 5.1 Control/State codes [已有代码结构；迁移中]

- `INVALID_STATE_TRANSITION`
- `ALREADY_IN_TARGET_STATE`
- `JOB_NOT_ACTIVE`
- `DELETE_PENDING_CLEANUP`
- `CONTROL_CONFLICT`

### 5.2 Access/Auth/Cooldown codes [已有代码结构]

- `auth_required`
- `invalid_credentials`
- `bootstrap_required`
- `guest_cookie_key_required`
- `guest_cooldown_active`

### 5.3 Naming convergence for error codes [规划中（planned）]

- Current contract accepts two stable code families:
  - Control/state: `UPPER_SNAKE_CASE`
  - Access/auth/cooldown: `lower_snake_case`
- Planned convergence will provide canonical + alias mapping before any breaking rename.

Rules:
- Do not change existing code meaning when introducing aliases.
- Error code meaning must stay stable across HTTP/event/audit surfaces.

## 6. Auth and Cooldown Contract Semantics

### 6.1 AuthSnapshot [规划中（planned）]

- Purpose: expose current auth mode/state to control-plane clients.
- Required:
  - `auth_mode` (for example `single_user` / `guest_enabled`)
  - `bootstrap_required` (boolean)
- Optional:
  - `last_updated_at`

### 6.2 CooldownSnapshot [规划中（planned）]

- Purpose: provide global guest submit cooldown semantics.
- Required:
  - `scope` (`global`)
  - `next_allowed_at`
- Optional:
  - `remaining_seconds`

Semantics:
- Cooldown is shared across all guest clients.
- A cooldown denial should return an error envelope with `guest_cooldown_active`.

## 7. Artifact Paths

Current canonical paths:
- `media/source.mp4` [已实现]
- `media/source.analysis.mp4` [已实现, optional]
- `asr/transcript.jsonl` [已实现]
- `frames/images/*.jpg` [已实现]
- `fusion/timeline.json` [已实现]
- `outputs/*.md|*.json|*.html` [已实现]

## 8. Versioning and Compatibility

- `schema_version` follows `major.minor`.
- Minor version: backward compatible additions.
- Major version: migration required and documented in ADR/release notes.
- Planned contracts may be introduced as optional fields first, then promoted to required in a major version.
