# Data Contracts

This document defines cross-module contract semantics for VideoSieve.
It is contract-oriented (meaning and boundaries), not implementation-oriented (SDK/ORM/runtime details).

## 1. Contract Principles

- Heavy data stays on workspace storage; persistence stores indexes, state snapshots, and references.
- 持久 JSON/JSONL 媒体产物包含 `schema_version`。当前 API snapshot 与 WS 信封尚未
  统一加入该字段，不能把目标版本字段写成线上事实。
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

### 2.2 Job [当前实现]

- Purpose: one execution run bound to a project.
- Snapshot required: `project_id`, `job_id`, `state_version`, `status`, `attempt`, `progress`,
  `latest_logs`, `artifacts`.
- Snapshot optional: `current_stage`, `requested_action`, `control_phase`, `control_request_id`,
  `error_code`, `error_message`.
- SQLite job rows additionally retain worker ownership/heartbeat and control request/ack versions.
- Immutable execution config is stored at `meta/config.snapshot.json`; the current SQLite row does
  not duplicate its path.

Example:
```json
{
  "job_id": "j_20260208_001",
  "project_id": "p_20260208_001",
  "status": "running",
  "requested_action": "pause",
  "state_version": 27,
  "attempt": 2,
  "progress": 42.5,
  "latest_logs": [],
  "artifacts": []
}
```

`status` is the canonical current snapshot field. A future rename to `execution_state` would require
a versioned migration; this document does not make that planned name available today.

### 2.3 JobAttempt [future schema]

- Required: `attempt_id`, `job_id`, `worker_id`, `status`, `started_at`, `heartbeat_at`
- Optional: `finished_at`, `end_reason`, `resume_from`, `parent_attempt_id`
- Current SQLite stores only the current worker ID, numeric attempt counter and heartbeat on `jobs`;
  it does not retain a separate attempt history.
- A heartbeat timeout may set the job to interrupted, but cannot create a replacement attempt.

### 2.4 ControlRequest [当前最小实现]

- The job row stores the latest `request_id`, command, request/ack versions and timestamps.
- WebSocket `control_ack` exposes `request_id`, command outcome and `accepted|applied|rejected` phase.
- A separate append-only control-request history table is not implemented.
- `phase` is `accepted|applied|rejected|failed`; accepted never proves computation stopped.

### 2.5 StageState [workspace checkpoint]

- Purpose: pipeline checkpoint 中的 per-stage 状态；当前没有 `job_stages` 数据库表。
- Required:
  - `schema_version`
  - `project_id`
  - `job_id`
  - `stage`
  - `status`
  - `updated_at`
- Optional:
  - `pct` (0-100)

### 2.6 Snapshot and Event Baseline [当前实现]

- `snapshot`: point-in-time state record, delivered through WebSocket after session establishment.
- `event`: SQLite-persisted append record with a monotonically increasing `event_id` cursor.
- Snapshot is authoritative for current state; retained events restore incremental history.
- Reconnect uses `after_cursor`. Event expiry and explicit `cursor_reset` are not implemented because
  current `job_events` rows are not automatically pruned.

## 3. Media and Processing Artifacts

### 3.1 TranscriptSegment (`asr/transcript.jsonl`) [schema 1.1]

- Required: `schema_version`, `segment_id`, `start`, `end`, `text`, `lang`
- Optional: `conf`（仅在 provider 实际返回置信度时写入）

Example JSONL line:
```json
{"schema_version":"1.1","segment_id":"seg_00001","start":0.2,"end":4.8,"text":"今天我们来讲线性变换。","lang":"zh","conf":0.93}
```

Migration note：旧 `1.0` 行要求 `conf`；`1.1` 将其改为可选，CapsWriter 未提供置信度时
省略该字段。读取方须同时接受 `1.0` 与 `1.1`；已有 job 产物不做原地改写。

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

### 3.5 ArtifactDescriptor [当前 final deliverables]

- `deliverables.ready.json` requires project/job identity, generation ID, source/config hashes,
  coverage/provenance and an artifact list.
- Each artifact entry requires `artifact_type`, job-relative `path`, `size_bytes` and `sha256`.
- API returns only entries whose manifest and canonical file still match.

### 3.6 Artifact realtime semantics [部分实现]

- `artifact_ready` is an event signal only; durability is confirmed by artifact snapshot/read API.
- Repeated `artifact_ready` for the same artifact is idempotent and acceptable.
- Client/UI should converge to latest snapshot if event loss occurs.
- A dedicated `artifact_ready` publication for every deliverable remains incomplete; snapshot/API
  manifest validation is the current readiness authority.

## 4. Event Envelope and Error Envelope

### 4.1 EventEnvelope [当前实现]

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

Connection-level `snapshot` is not a persisted event row. `cursor_reset` is reserved but not yet
implemented. Ordering and deduplication use the persisted `event_id`, exposed to WS clients as
`cursor`, not timestamps.

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
