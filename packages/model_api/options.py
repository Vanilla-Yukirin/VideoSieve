"""Validated, non-secret model settings shared by API, snapshots and workers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_INPUT_RESERVE_TOKENS = 2048
SUMMARY_PROMPT_RESERVE_TOKENS = 2048
SUMMARY_UTF8_BYTES_PER_CHAR = 4
SUMMARY_MIN_INPUT_CHARS = 1000
SUMMARY_MIN_CONTEXT_OUTPUT_GAP = (
    MODEL_INPUT_RESERVE_TOKENS
    + SUMMARY_PROMPT_RESERVE_TOKENS
    + SUMMARY_UTF8_BYTES_PER_CHAR * SUMMARY_MIN_INPUT_CHARS
)


class ModelRequestOptions(BaseModel):
    """Local context budget is a ceiling, not a claim about the provider's model."""

    model_config = ConfigDict(extra="ignore", strict=True)

    context_window_tokens: int = Field(default=131_072, ge=4096, le=4_194_304)
    max_output_tokens: int = Field(default=32_768, ge=128, le=1_048_576)
    thinking_enabled: bool = True
    thinking_adapter: Literal[
        "auto", "openai", "openai_legacy", "deepseek", "dashscope",
        "anthropic_budget", "anthropic_adaptive"
    ] = "auto"
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    thinking_budget_tokens: int = Field(default=8192, ge=1024, le=1_048_576)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)

    @model_validator(mode="after")
    def validate_budget(self) -> "ModelRequestOptions":
        if self.max_output_tokens + MODEL_INPUT_RESERVE_TOKENS >= self.context_window_tokens:
            raise ValueError("context window must leave more than 2048 tokens beyond output budget")
        if self.thinking_adapter == "openai_legacy" and self.thinking_enabled:
            raise ValueError("OpenAI legacy models do not support enabled reasoning")
        return self

    @property
    def summary_input_char_budget(self) -> int:
        """Conservative batching budget, separate from provider-reported token usage."""
        return (
            self.context_window_tokens
            - self.max_output_tokens
            - MODEL_INPUT_RESERVE_TOKENS
            - SUMMARY_PROMPT_RESERVE_TOKENS
        ) // SUMMARY_UTF8_BYTES_PER_CHAR

    def require_summary_input_budget(self) -> int:
        """Validate the same summary boundary before saving/testing and in the worker."""
        budget = self.summary_input_char_budget
        if budget < SUMMARY_MIN_INPUT_CHARS:
            raise ValueError(
                "overall summary context budget must exceed maximum output by at least "
                f"{SUMMARY_MIN_CONTEXT_OUTPUT_GAP} tokens to reserve summary input"
            )
        return budget
