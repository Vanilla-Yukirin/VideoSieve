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

- `ingest.source_url`, `ingest.video_format_id`, `ingest.audio_format_id`
- `ingest.ytdlp_format`, `ingest.ytdlp_sort`, `ingest.download_retries`
- `ingest.cookie_file_path`, `ingest.cookie_secret_ref`
- `asr.provider`, `asr.language_hint`, `asr.hotword_enabled`
- `keyframes.strategy`, `keyframes.sample_fps`, `keyframes.threshold`
- `ocr.provider`, `ocr.min_conf`
- `pipeline.max_retries`, `pipeline.timeout`

Notes:
- `video_format_id` + `audio_format_id` are the default quality-selection path.
- `ytdlp_format` / `ytdlp_sort` are advanced options for expert users.
- API/Web must not accept raw `cookie_content`; use `cookie_file_path` or `cookie_secret_ref`.

## 4. Validation

- Validate on API write
- Re-validate at job start
