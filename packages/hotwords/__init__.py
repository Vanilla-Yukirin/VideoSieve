"""Rule-based hotwords extraction MVP."""

from .models import HotwordItem, HotwordsDocument, HotwordsResult
from .service import run_hotwords, run_hotwords_from_meta

__all__ = [
    "HotwordItem",
    "HotwordsDocument",
    "HotwordsResult",
    "run_hotwords",
    "run_hotwords_from_meta",
]
