# Workspace Layout

Canonical runtime structure (single source for workspace paths):

```text
workspaces/{project_id}/
  uploads/                       # API 接收的本地文件 staging，仅本项目 job 可引用
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
      deliverables.ready.json    # 最后发布；含文件大小和 SHA-256
      export.html
    logs/
      worker.log
```

## Lifecycle

- job 创建成功后初始化目录；目录创建失败必须使 job 明确失败
- 重跑创建新的 `job_id`，不清空或覆盖旧 job 目录
- 当前 deliverables 写同目录的 generation 临时文件，校验完成后替换 canonical 文件，
  并最后发布 `deliverables.ready.json`
- API 只有在 readiness manifest 的 project/job 身份、文件大小和 SHA-256 全部匹配时，
  才暴露最终 deliverables
- `.attempts/{attempt_id}/tmp` 尚未实现；其它中间阶段仍依赖 checkpoint 和各自写入逻辑，
  不能宣称已获得 attempt 级原子发布
- delete follows two-phase rule (`cancel` -> confirmed stopped -> cleanup)
- 路径构造必须限制在 canonical workspace root，拒绝路径穿越和符号链接逃逸
