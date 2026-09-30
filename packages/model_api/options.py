"""Validated, non-secret model settings shared by API, snapshots and workers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRequestOptions(BaseModel):
    """Local context budget is a ceiling, not a claim about the provider's model."""

    model_config = ConfigDict(extra="ignore", strict=True)

    context_window_tokens: int = Field(default=131_072, ge=4096, le=4_194_304)
    max_output_tokens: int = Field(default=32_768, ge=128, le=1_048_576)
    thinking_enabled: bool = True
    thinking_adapter: Literal[
        "auto", "openai", "deepseek", "dashscope", "anthropic_budget", "anthropic_adaptive"
    ] = "auto"
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    thinking_budget_tokens: int = Field(default=8192, ge=1024, le=1_048_576)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)

    @model_validator(mode="after")
    def validate_budget(self) -> "ModelRequestOptions":
        if self.max_output_tokens + 2048 >= self.context_window_tokens:
            raise ValueError("context window must leave more than 2048 tokens beyond output budget")
        return self
