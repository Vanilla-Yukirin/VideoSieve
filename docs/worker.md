# Execution Mode

This repository now uses a single-agent execution workflow by default.

## Policy

- One agent owns end-to-end implementation for aligned architecture and contracts.
- Parallel worker split is disabled unless a task is clearly unrelated and isolated.
- Planning, code, docs, and tests should land in one coherent change set.

## Current Technical Direction

- Single-host trusted mode; product access control belongs to the outer deployment boundary.
- ASR runs in an external service selected through the provider adapter. The worker only
  normalizes media with FFmpeg and performs the remote request.
- Frame understanding runs as FrameSummary-only with free-text outputs.
- One VLM request per frame, free-text output allowed (no mandatory JSON schema from model).
- Timeline and deliverables consume VLM output as evidence text.
