# Data Contracts

## 1. Principles

- Heavy data on disk; DB stores indexes/state only
- All contracts include `schema_version`
- Additive fields preferred; breaking changes require migration note

`schema_version` placement:
- JSON 文件（如 `timeline.json`）：放在顶层字段
- JSONL 文件（如 `transcript.jsonl`）：每行对象包含 `schema_version`

## 2. Canonical Objects

### Project
- Fields: `project_id`, `source_type`, `source_ref`, `title`, `status`, `created_at`

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

### Job
- Fields: `job_id`, `project_id`, `config_snapshot_path`, `status`, `started_at`, `finished_at`

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

### IngestMeta (`meta/meta.json`)
- Fields: `project_id`, `job_id`, `source_type`, `source_ref`, `title`, `description`, `tags`, `ingested_at`
- Optional downloader fields: `uploader`, `duration_seconds`, `webpage_url`
- Optional quality-selection fields:
  - `selected_format`
  - `selected_video_format_id`
  - `selected_audio_format_id`

Example:
```json
{
  "schema_version": "1.0",
  "project_id": "p_20260208_001",
  "job_id": "j_20260208_009",
  "source_type": "bilibili_url",
  "source_ref": "https://www.bilibili.com/video/BV...",
  "title": "Linear Algebra Lecture 01",
  "selected_format": "30116+30280",
  "selected_video_format_id": "30116",
  "selected_audio_format_id": "30280",
  "ingested_at": "2026-02-09T12:00:00Z"
}
```

### IngestProbeResponse (`POST /ingest/probe`)
- Required per format item:
  - `format_id`, `resolution`, `fps`, `tbr`, `vcodec`, `acodec`, `is_video_only`, `is_audio_only`
- Optional per item: `ext`, `protocol`, `filesize_approx`

Example:
```json
{
  "source_url": "https://www.bilibili.com/video/BV...",
  "title": "Linear Algebra Lecture 01",
  "formats": [
    {
      "format_id": "30116",
      "resolution": "1920x1080",
      "fps": 60,
      "tbr": 1359,
      "vcodec": "avc1.640033",
      "acodec": "none",
      "is_video_only": true,
      "is_audio_only": false
    }
  ]
}
```

### TranscriptSegment (`asr/transcript.jsonl`)
- Fields: `segment_id`, `start`, `end`, `text`, `lang`, `conf`

Example JSONL line:
```json
{"schema_version":"1.0","segment_id":"seg_00001","start":0.2,"end":4.8,"text":"今天我们来讲线性变换。","lang":"zh","conf":0.93}
```

### Keyframe (`frames/keyframes.jsonl`)
- Fields: `frame_id`, `ts`, `path`, `hash`, `score`, `reason`

Example JSONL line:
```json
{"schema_version":"1.0","frame_id":"frame_00012","ts":126.4,"path":"workspaces/p_20260208_001/frames/images/slide_000012.jpg","hash":"a91f...","score":0.82,"reason":"stable"}
```

### OCRResult (`ocr/ocr.jsonl`)
- Fields: `frame_id`, `blocks[]`, `lang`, `conf`

Example JSONL line:
```json
{"schema_version":"1.0","frame_id":"frame_00012","lang":"zh","conf":0.89,"blocks":[{"text":"特征值与特征向量","bbox":[120,80,640,160],"conf":0.92}]}
```

### Timeline (`fusion/timeline.json`)
- Fields: `chunks[]`, each chunk includes transcript refs, frame refs, ocr refs, text

Example:
```json
{
  "schema_version": "1.0",
  "project_id": "p_20260208_001",
  "job_id": "j_20260208_001",
  "chunks": [
    {
      "chunk_id": "ch_0001",
      "start": 120.0,
      "end": 165.0,
      "text": "这一段讲了特征分解的几何意义。",
      "transcript_refs": ["seg_00038", "seg_00039"],
      "frame_refs": ["frame_00012"],
      "ocr_refs": ["frame_00012:block_0001"]
    }
  ]
}
```

## 3. Artifact Paths

- `media/source.mp4`
- `asr/transcript.jsonl`
- `frames/images/*.jpg`
- `fusion/timeline.json`
- `outputs/*.md|*.json|*.html`

## 4. Versioning

- `schema_version` follows `major.minor`
- Minor: backward compatible
- Major: migration required and documented in ADR/release notes
