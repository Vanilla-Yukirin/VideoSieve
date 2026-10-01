export const MODEL_REQUEST_DEFAULTS = {
  context_window_tokens: 131072,
  max_output_tokens: 32768,
  thinking_enabled: true,
  thinking_adapter: "auto",
  reasoning_effort: "medium",
  thinking_budget_tokens: 8192,
  max_retries: 2,
  timeout_seconds: 300,
} as const;

// Match the summary worker's prompt reserve and conservative 4-byte character budget.
export const SUMMARY_MIN_CONTEXT_OUTPUT_GAP = 2048 + 2048 + 4 * 1000;
