"""
app/agent/state.py - Persona and Approved Fake Bait State for GuardianLine.
"""

from typing import Any, Dict, List, Optional
from app.core.rules import APPROVED_BAIT_VALUES, APPROVED_PERSONAS

SUPPORTED_LANGUAGES = {"hi", "en", "hinglish"}
PERSONA_ORDER: List[str] = ["ramesh", "sunita", "iyer"]


def normalize_language(language: Optional[str]) -> str:
    """Normalize language string; unknown language falls back to 'hi' (Hindi)."""
    if not language:
        return "hi"
    low = str(language).lower().strip()
    if low in {"hi", "hindi", "hi-in"}:
        return "hi"
    if low in {"en", "english", "en-in", "en-us"}:
        return "en"
    if low in {"hinglish", "hi-en"}:
        return "hinglish"
    return "hi"


def get_persona_bundle(call_id: str, language: Optional[str] = "hi", preferred_persona: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministically select or retrieve an approved persona and fake bait for `call_id`.
    """
    lang = normalize_language(language)
    if preferred_persona and preferred_persona.lower() in APPROVED_PERSONAS:
        p_key = preferred_persona.lower()
    else:
        # Default Sprint 1 primary persona is 'ramesh', or deterministic selection if specified
        p_key = "ramesh"

    persona = APPROVED_PERSONAS[p_key]
    lines = persona["lines"].get(lang, persona["lines"]["hi"])

    return {
        "call_id": call_id,
        "language": lang,
        "persona_id": persona["persona_id"],
        "persona_name": persona["persona_name"],
        "persona_age": persona["persona_age"],
        "persona_city": persona["persona_city"],
        "persona_lines": list(lines),
        "fake_bait": dict(persona["fake_bait"]),
    }


__all__ = [
    "APPROVED_PERSONAS",
    "APPROVED_BAIT_VALUES",
    "SUPPORTED_LANGUAGES",
    "normalize_language",
    "get_persona_bundle",
]
