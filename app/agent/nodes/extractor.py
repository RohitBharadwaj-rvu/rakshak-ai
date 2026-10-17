"""Compatibility re-export of GuardianLine transcript extractor."""

from app.voice.extractor import (
    extract_entities_from_text,
    extract_from_transcript,
    normalize_and_validate_single_intel,
)

__all__ = [
    "extract_entities_from_text",
    "extract_from_transcript",
    "normalize_and_validate_single_intel",
]
