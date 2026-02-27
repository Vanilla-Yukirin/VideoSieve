"""Keyframe baseline extraction package."""

from .algorithm import CandidateFrame, FrameFeature
from .extractor import extract_video_features, write_images_for_records
from .models import ALLOWED_KEYFRAME_REASONS, KeyframeRecord
from .service import (
    KeyframeAlgorithmService,
    KeyframeBaselineService,
    KeyframeRunDiagnostics,
    build_images_zip,
)

__all__ = [
    "ALLOWED_KEYFRAME_REASONS",
    "CandidateFrame",
    "build_images_zip",
    "extract_video_features",
    "FrameFeature",
    "KeyframeAlgorithmService",
    "KeyframeBaselineService",
    "KeyframeRunDiagnostics",
    "KeyframeRecord",
    "write_images_for_records",
]
