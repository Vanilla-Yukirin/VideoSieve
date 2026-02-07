# Workspace Layout

Canonical runtime structure (single source for workspace paths):

```text
workspaces/{project_id}/
  meta/
    meta.json
    config.snapshot.json
  media/
    source.mp4
    audio.wav
  hotwords/
    hotwords.json
    vocabulary_ref.json
  asr/
    transcript.jsonl
    transcript.words.jsonl
  frames/
    keyframes.jsonl
    images/*.jpg
    metrics/diff_curve.csv
  ocr/
    ocr.jsonl
  fusion/
    timeline.json
  outputs/
    clean_transcript.md
    illustrated_notes.md
    summary.json
    export.html
  logs/
    worker.log
```

## Lifecycle

- create on project/job start
- preserve for rerun when compatible
- delete follows two-phase rule (`cancel` -> cleanup)
