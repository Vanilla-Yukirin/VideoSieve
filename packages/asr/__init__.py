"""ASR contracts and external provider selection."""

from .capswriter import CapsWriterWebSocketProvider
from .factory import create_asr_provider_from_config, create_asr_provider_from_env
from .interfaces import ASRProvider, ASRProviderError
from .models import TRANSCRIPT_SCHEMA_VERSION, ASRRequest, ASRResult, ASRSegment
from .service import write_transcript_jsonl

__all__ = [
    "ASRProvider",
    "ASRProviderError",
    "ASRRequest",
    "ASRResult",
    "ASRSegment",
    "TRANSCRIPT_SCHEMA_VERSION",
    "CapsWriterWebSocketProvider",
    "create_asr_provider_from_config",
    "create_asr_provider_from_env",
    "write_transcript_jsonl",
    "__version__",
]

__version__ = "0.1.0"
