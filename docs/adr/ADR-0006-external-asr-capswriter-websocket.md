# ADR-0006: External ASR through CapsWriter WebSocket

- Status: Accepted
- Date: 2026-09-20

## Context

VideoSieve is a single-host media workflow and asset platform, not a speech-model
distribution. Bundling FunASR, PyTorch, Torchaudio, Transformers, model downloads and
upstream patches made the base installation heavy and coupled product releases to one
model runtime. The user already operates a separate CapsWriter service and wants other
deployments to connect their own service.

CapsWriter upstream defines a root WebSocket protocol. Clients send Base64 encoded
float32, 16 kHz, mono audio messages and receive final text, tokens and timestamps.
Upstream does not require authentication.

## Decision

- VideoSieve ships no ASR model runtime or model files.
- ASR is `unconfigured` until an administrator selects an external provider.
- The first production adapter is `capswriter` using the upstream WebSocket protocol.
- The worker uses FFmpeg to normalize media and sends bounded audio chunks.
- `CAPSWRITER_TOKEN` is an optional Bearer header for deployments that add authentication.
  The credential stays in the worker environment; SQLite and job snapshots contain only
  the credential name.
- VideoSieve does not expose the deployment-specific HTTP transcription extension as a
  product contract. Future ASR providers require a separate adapter and documented tests.

## Consequences

The base dependency graph is much smaller and installing VideoSieve cannot download an
ASR model. A working deployment must operate or purchase a separate ASR service and keep
FFmpeg available on the worker host. Provider failure is a task failure; no mock transcript
or local fallback is generated.

Automated tests cover protocol messages, optional authentication, response parsing,
configuration snapshots and explicit failures. Real service quality and timestamp accuracy
still require a real-media acceptance record.
