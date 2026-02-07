"""ASR module interfaces and baseline provider."""

from .baseline import BaselineASRProvider
from .interfaces import ASRProvider
from .models import ASRRequest, ASRResult, ASRSegment
from .service import write_transcript_jsonl

__all__ = [
    "ASRProvider",
    "ASRRequest",
    "ASRResult",
    "ASRSegment",
    "BaselineASRProvider",
    "write_transcript_jsonl",
    "__version__",
]

__version__ = "0.1.0"
