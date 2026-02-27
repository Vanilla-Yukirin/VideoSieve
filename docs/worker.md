# Execution Mode

This repository now uses a single-agent execution workflow by default.

## Policy

- One agent owns end-to-end implementation for aligned architecture and contracts.
- Parallel worker split is disabled unless a task is clearly unrelated and isolated.
- Planning, code, docs, and tests should land in one coherent change set.

## Current Technical Direction

- Single-user first, guest mode optional and disabled by default.
- ASR runs locally on server runtime.
- Frame understanding runs as FrameSummary-only with free-text outputs.
- One VLM request per frame, free-text output allowed (no mandatory JSON schema from model).
- Timeline and deliverables consume VLM output as evidence text.
