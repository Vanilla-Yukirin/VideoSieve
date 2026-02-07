"""OCR adapter and baseline mock provider package."""

from .providers import OCRBlock, OCRFrameResult, OCRProvider
from .service import MockOCRProvider, OCRBaselineService

__all__ = [
    "MockOCRProvider",
    "OCRBaselineService",
    "OCRBlock",
    "OCRFrameResult",
    "OCRProvider",
]
