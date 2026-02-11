# Configuration

## 1. Scope and Status

Status labels used in this document:
- `Implemented` = behavior already implemented in current infra persistence layer.
- `Planned` = target behavior defined as contract; requires app/bootstrap wiring.

## 2. Configuration Layers (Who Decides)

1. Deployment layer (`Env`)
- Purpose: deployment constraints and sensitive runtime inputs.
- Typical location: container/service env vars.

2. System settings layer (`DB: system_settings`)
- Purpose: mutable product switches managed after login.
- Source of truth after initialization.

3. Runtime snapshot layer (`meta/config.snapshot.json`)
- Purpose: freeze job-time configuration for reproducibility.
- Immutable once a job is created.

Decision priority:
- First bootstrap: `Env -> DB` initialize missing keys once. `Implemented` (for current system settings keys)
- After bootstrap: runtime reads `DB` values for system switches. `Implemented`
- During job execution: read snapshot, not mutable settings/UI state. `Implemented` (contract)

## 3. Access and Guest Keys

Deployment keys (Env):
- `APP_SECRET_KEY`
- `ENABLE_GUEST_MODE`
- `GUEST_ALLOW_COOKIE_INPUT`
- `GUEST_COOKIE_KEY`
- `GUEST_JOB_COOLDOWN_SECONDS`

System settings keys (DB-facing naming):
- `guest_mode_enabled`
- `guest_allow_cookie_input`
- `guest_job_cooldown_seconds`

Notes:
- Env names are deployment-facing; DB names are product-facing persisted flags.
- Mapping from Env keys to DB keys at first bootstrap is implemented for current system settings keys.
- `system_settings` persistence (get/set upsert) exists in infra repository. `Implemented`

## 4. Guest Config Legality and Rejection Rules

Required legality rule:
- if `guest_allow_cookie_input=true`, then `GUEST_COOKIE_KEY` must be non-empty.

Rejection semantics:
- Startup path should fail fast on illegal combination. `Implemented`
- Settings write path should reject illegal updates with explicit error code
  `guest_cookie_key_required`. `Implemented`
- Illegal config must never silently downgrade into ambiguous behavior.

## 5. Cookie-Related Config and Entry Points

Job/config keys:
- `ingest.cookie_id` (preferred)
- `ingest.cookie_file_path` (migration fallback only)
- `ingest.cookie_secret_ref`

Operational policy:
- API/Web create-job path should use `cookie_id`; avoid raw cookie plaintext fields.
- `cookie_file_path` is a compatibility fallback and should not be the primary path.

Status:
- Cookie vault persistence in infra repository exists (`user_cookies` table methods). `Implemented`
- End-to-end enforcement of create-job input restrictions is app-layer behavior. `Planned`

## 6. Local vs Deployment vs Runtime (Operator View)

- Local/dev deployment can set Env defaults for initial bootstrap.
- Production deployment should set all required Env keys explicitly.
- Once DB settings are seeded, operators should treat DB as current effective state.
- Running jobs do not follow live setting flips; they follow their snapshot.

## 7. Validation Checklist

- Validate settings on write (API/settings layer). `Implemented`
- Re-validate at job creation and snapshot freeze boundary. `Planned`
- Ensure cooldown and guest policy values are auditable through operation logs. `Implemented`
