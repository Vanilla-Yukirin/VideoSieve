"""Protocol adapters for externally hosted language and vision models."""

from .client import (
    MODEL_PROTOCOLS,
    ModelApiError,
    request_model_text,
    resolve_model_endpoint,
)

__all__ = [
    "MODEL_PROTOCOLS",
    "ModelApiError",
    "request_model_text",
    "resolve_model_endpoint",
]
