"""ASR contracts and production provider selection."""

from .factory import create_asr_provider_from_env
from .funasr_local import FunASRLocalProvider
from .interfaces import ASRProvider
from .models import ASRRequest, ASRResult, ASRSegment
from .service import write_transcript_jsonl

__all__ = [
    "ASRProvider",
    "ASRRequest",
    "ASRResult",
    "ASRSegment",
    "FunASRLocalProvider",
    "create_asr_provider_from_env",
    "write_transcript_jsonl",
    "__version__",
]

__version__ = "0.1.0"
