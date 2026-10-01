"""Protocol adapters for externally hosted language and vision models."""

from .client import (
    MODEL_PROTOCOLS,
    ModelApiError,
    ModelResponse,
    request_model,
    request_model_text,
    resolve_model_endpoint,
)
from .options import ModelRequestOptions
from .telemetry import ModelCallAttempt, ModelCallJournal, read_usage_summary

__all__ = [
    "MODEL_PROTOCOLS",
    "ModelApiError",
    "ModelResponse",
    "ModelRequestOptions",
    "ModelCallAttempt",
    "ModelCallJournal",
    "read_usage_summary",
    "request_model",
    "request_model_text",
    "resolve_model_endpoint",
]
