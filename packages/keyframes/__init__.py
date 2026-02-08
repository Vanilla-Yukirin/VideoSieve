"""Keyframe baseline extraction package."""

from .algorithm import CandidateFrame, FrameFeature
from .extractor import extract_video_features, write_images_for_records
from .models import ALLOWED_KEYFRAME_REASONS, KeyframeRecord
from .service import KeyframeAlgorithmService, KeyframeBaselineService, KeyframeRunDiagnostics

__all__ = [
    "ALLOWED_KEYFRAME_REASONS",
    "CandidateFrame",
    "extract_video_features",
    "FrameFeature",
    "KeyframeAlgorithmService",
    "KeyframeBaselineService",
    "KeyframeRunDiagnostics",
    "KeyframeRecord",
    "write_images_for_records",
]
