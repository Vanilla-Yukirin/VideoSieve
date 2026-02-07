# Configuration

## 1. Layers

- Global defaults
- Project overrides
- Job snapshot (immutable runtime view)

## 2. Principles

- Every run writes `meta/config.snapshot.json`
- Runtime reads snapshot, not mutable UI state
- Config changes are auditable

## 3. Suggested Keys

- `asr.provider`, `asr.language_hint`, `asr.hotword_enabled`
- `keyframes.strategy`, `keyframes.sample_fps`, `keyframes.threshold`
- `ocr.provider`, `ocr.min_conf`
- `pipeline.max_retries`, `pipeline.timeout`

## 4. Validation

- Validate on API write
- Re-validate at job start
