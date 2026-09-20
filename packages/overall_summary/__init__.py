"""Model-backed overall summary package."""

from .evidence import (
    EvidenceSection,
    EvidenceValidationError,
    TimelineEvidence,
    evidence_sha256,
    read_frame_summary_evidence,
    read_timeline_evidence,
    sha256_file,
    sha256_json,
    sha256_text,
)
from .providers import (
    OverallSummaryProvider,
    OverallSummaryProviderError,
    OverallSummaryResult,
    SummaryProviderProvenance,
)
from .service import OpenAICompatibleSummaryProvider, OverallSummaryService

__all__ = [
    "EvidenceSection",
    "EvidenceValidationError",
    "OpenAICompatibleSummaryProvider",
    "OverallSummaryProvider",
    "OverallSummaryProviderError",
    "OverallSummaryResult",
    "OverallSummaryService",
    "SummaryProviderProvenance",
    "TimelineEvidence",
    "evidence_sha256",
    "read_frame_summary_evidence",
    "read_timeline_evidence",
    "sha256_file",
    "sha256_json",
    "sha256_text",
]
