# Workspace Layout

Canonical runtime structure (single source for workspace paths):

```text
workspaces/{project_id}/
  jobs/{job_id}/
    meta/
      meta.json
      config.snapshot.json
      pipeline.checkpoint.json
    media/
      source.mp4
      source.analysis.mp4
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
      metrics/selection_trace.jsonl
      metrics/timing_report.json
    frame_summary/
      frame_summary.jsonl
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

- create on job start
- rerun cleans current job directory then executes full pipeline
- delete follows two-phase rule (`cancel` -> cleanup)
