"""VLM-only frame understanding adapter package."""

from .providers import OCRBlock, OCRFrameResult, OCRProvider
from .service import MockOCRProvider, OCRBaselineService, VLMOnlyProvider

__all__ = [
    "MockOCRProvider",
    "VLMOnlyProvider",
    "OCRBaselineService",
    "OCRBlock",
    "OCRFrameResult",
    "OCRProvider",
]
