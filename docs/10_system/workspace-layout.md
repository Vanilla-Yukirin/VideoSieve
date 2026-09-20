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
    .attempts/
      {attempt_id}/
        tmp/                    # 未发布文件，不对 API/UI 可见
```

## Lifecycle

- job 创建成功后初始化目录；目录创建失败必须使 job 明确失败
- 重跑创建新的 `job_id`，不清空或覆盖旧 job 目录
- stage 内先写 `.attempts/{attempt_id}/tmp`，校验后在同一文件系统原子发布
- 只有数据库登记后的 canonical path 才能作为 ready artifact 暴露
- interrupted attempt 的临时目录保留到恢复判定，不与新 attempt 混用
- delete follows two-phase rule (`cancel` -> confirmed stopped -> cleanup)
- 路径构造必须限制在 canonical workspace root，拒绝路径穿越和符号链接逃逸
