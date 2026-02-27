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

### 2.1 Project [已实现]

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

### 2.2 Job [已实现]

- Purpose: one execution run bound to a project.
- Required:
  - `schema_version`
  - `job_id`
  - `project_id`
  - `config_snapshot_path`
  - `status`
- Optional:
  - `started_at`
  - `finished_at`

Example:
```json
{
  "schema_version": "1.0",
  "job_id": "j_20260208_001",
  "project_id": "p_20260208_001",
  "config_snapshot_path": "workspaces/p_20260208_001/meta/config.snapshot.json",
  "status": "running",
  "started_at": "2026-02-08T10:00:05Z",
  "finished_at": null
}
```

### 2.3 StageState [已实现]

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

### 2.4 Snapshot and Event Baseline [已实现]

- `snapshot`: point-in-time state record (source of truth for recovery/reconnect).
- `event`: append-style change signal (best-effort delivery allowed depending on bus mode).
- Snapshot is authoritative; event stream is incremental.

## 3. Media and Processing Artifacts

### 3.1 TranscriptSegment (`asr/transcript.jsonl`) [已实现]

- Required: `schema_version`, `segment_id`, `start`, `end`, `text`, `lang`, `conf`

Example JSONL line:
```json
{"schema_version":"1.0","segment_id":"seg_00001","start":0.2,"end":4.8,"text":"今天我们来讲线性变换。","lang":"zh","conf":0.93}
```

### 3.2 Keyframe (`frames/keyframes.jsonl`) [已实现]

- Required: `schema_version`, `frame_id`, `ts`, `path`, `hash`, `score`, `reason`

Example JSONL line:
```json
{"schema_version":"1.0","frame_id":"frame_00012","ts":126.4,"path":"workspaces/p_20260208_001/frames/images/slide_000012.jpg","hash":"a91f...","score":0.82,"reason":"stable"}
```

### 3.3 FrameSummary (`frame_summary/frame_summary.jsonl`) [已实现]

- Required: `schema_version`, `frame_id`, `lang`, `provider`, `description_text`

Example JSONL line:
```json
{"schema_version":"1.1","frame_id":"frame_00012","lang":"zh","provider":"qwen_frame_summary","description_text":"画面上半部分是标题“特征值与特征向量”，下半部分是公式推导说明。"}
```

### 3.4 Timeline (`fusion/timeline.json`) [已实现]

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

### 4.1 EventEnvelope [已实现]

- Required:
  - `schema_version`
  - `event_type`
  - `project_id`
  - `job_id`
  - `ts`
  - `payload`

Known `event_type` values:
- `log`
- `progress`
- `stage_changed`
- `error`
- `control_ack`

Planned additional event types:
- `artifact_ready`
- `artifact_removed`
- `snapshot_hint`

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

### 5.1 Control/State codes [已实现]

- `INVALID_STATE_TRANSITION`
- `ALREADY_IN_TARGET_STATE`
- `JOB_NOT_ACTIVE`
- `DELETE_PENDING_CLEANUP`
- `CONTROL_CONFLICT`

### 5.2 Access/Auth/Cooldown codes [已实现]

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
