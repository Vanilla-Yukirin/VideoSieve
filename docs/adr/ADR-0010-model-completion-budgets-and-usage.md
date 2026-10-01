# ADR-0010: Model Completion, Budgets and Provider Usage

Status: Accepted

Date: 2026-10-01

## Context

The old client accepted any non-empty model text, discarded completion/usage fields,
and fixed Anthropic output at 1,024 tokens. Valid JSON did not ensure a complete answer.

## Decision

- Use official OpenAI and Anthropic SDK transports with SDK retries disabled. The
  protocol adapter owns wire parameters, completion checks and observable retries.
- Profile defaults: local context budget 131,072, output ceiling 32,768, reasoning
  enabled, two additional retries and 300 seconds per request. The Web modal edits
  these plus reasoning adapter/effort and Anthropic thinking budget (default 8192).
  New jobs freeze them in `model_options`; changing profiles does not rewrite jobs.
- Local context budget controls conservative UTF-8 guards and hierarchical batching,
  not the provider's actual model window. Images/tokenizers need upstream validation.
  These guards never become usage estimates. Reserve output and prompt space.
  Overall-summary batching shares one calculation across API and worker:
  `(context_window_tokens - max_output_tokens - 4096) // 4` characters.
  A minimum 1,000-character batch requires a gap of at least 8,096. Reject smaller
  summary budgets before saving, testing or queuing an enabled summary. Previously
  saved profiles remain readable/editable; old immutable jobs fail explicitly.
- Reasoning adapters: `auto`, `openai`, `openai_legacy`, `deepseek`, `dashscope`, `anthropic_budget`,
  `anthropic_adaptive`. Auto uses protocol/hostname. Proxies must choose explicitly.
  Standard OpenAI disabled reasoning explicitly sends effort `none`; unsupported
  settings fail visibly without silently removing the parameter. Non-reasoning
  models select `openai_legacy`, which omits reasoning and rejects enabling it.
  Anthropic budget is capped below output; adaptive uses `output_config.effort`
  and delegates the actual thinking allocation to the model.
- Standard OpenAI Chat uses `max_completion_tokens` whether reasoning is enabled or
  disabled. Legacy and compatible Chat use
  `max_tokens`, Responses uses `max_output_tokens`, Anthropic uses `max_tokens`.
  Output budgets may include thinking tokens. No generic temperature is forced.
- Accept Chat `stop`, Responses `completed`, Anthropic `end_turn`/`stop_sequence`.
  Missing completion metadata, truncation, refusal, filtering, tool requests,
  malformed/empty responses never become successful prose. No tools are requested.
- Retry transient HTTP/transport and malformed/incomplete results with bounded
  backoff. Truncation retries keep all evidence, request a complete concise answer,
  discard partial text and retain the configured cap. Exhaustion is a stage failure.
  Authentication/configuration/filtering errors do not trigger blind retries.
  All visual request attempts, including retries, acquire the same per-run RPM
  gate. Rate waits remain cooperative and are excluded from request duration.
  Check task control before/after calls and during waits. A synchronous in-flight
  call can still take its timeout to return; no instant cancellation is promised.
- Keep natural-language outputs; validate the response envelope/completion, without
  forcing JSON mode. JSON syntax does not prove coverage or factual accuracy.
- Append provider numeric `usage`, request ID, stop reason, error code, protocol,
  model, worker attempt and monotonic request duration to `meta/model_calls.jsonl`.
  Never persist credentials, endpoints, prompts, reasoning text or response bodies
  in this journal. It includes failures/retries and all visual/map/reduce/final calls.
  Read and decode each row independently; a malformed JSON or incomplete UTF-8
  crash tail cannot hide complete history or prevent later appends. Preserve the
  damaged bytes as evidence and isolate them with a newline before appending.
- WS `model_usage` events carry cumulative stage totals. Snapshots rebuild from the
  journal. Missing counters stay unknown; partial sums are marked. Cache/reasoning
  fields have protocol-specific semantics and are not automatically added to input
  or output. Total tokens are only summed when reported upstream.
  Anthropic `output_tokens_details.thinking_tokens` maps to the displayed reasoning
  subtotal while the original usage is preserved; output remains inclusive.
  Cumulative usage merges by cursor and nondecreasing call count independently of
  task state version, so concurrent control acknowledgements cannot hide completed
  calls. This never rolls back task state/version or relaxes state-event fences.
  Network-inclusive durations overlap under concurrency; their sum is not wall time
  or TTFT. Historical tasks get no estimated backfill.
- Trusted single-host access stays unchanged: no new login, Origin rejection or
  TS/IPv4 routing changes, as explicitly requested by the user.

## Verification

Test SDK wire formats, completion/retry failures, preserved usage, immutable snapshots
and Web editing. Real provider smoke tests and video E2E are separate evidence; a
synthetic SDK transport test is not real inference or deployment authorization.

## Primary references

- [OpenAI SDK](https://github.com/openai/openai-python)
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python)
- [DeepSeek thinking](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
