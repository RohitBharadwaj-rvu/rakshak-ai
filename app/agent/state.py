"""
app/agent/state.py - Persona and Rotating Fake Bait State for GuardianLine.
"""

from typing import Any, Dict, List, Optional
from app.core.rules import (
    APPROVED_BAIT_VALUES,
    APPROVED_PERSONAS,
    PERSONA_KEYS,
    get_rotating_bait,
    verify_luhn,
)

SUPPORTED_LANGUAGES = {"hi", "en", "hinglish"}
PERSONA_ORDER: List[str] = list(PERSONA_KEYS)


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


def get_persona_bundle(
    call_id: str,
    language: Optional[str] = "hi",
    preferred_persona: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically select or retrieve an approved persona and rotating bait for `call_id`.
    When `preferred_persona` is not specified, rotates across all 20 personas using
    `get_rotating_bait(call_id)` (seeded via `hashlib.sha256(call_id).digest()`).
    """
    lang = normalize_language(language)
    if preferred_persona and preferred_persona.lower() in APPROVED_PERSONAS:
        p_key = preferred_persona.lower()
        persona = APPROVED_PERSONAS[p_key]
        bait_copy = dict(persona["fake_bait"])
    else:
        rotated = get_rotating_bait(call_id)
        p_key = rotated["persona_id"]
        persona = APPROVED_PERSONAS[p_key]
        bait_copy = dict(rotated["fake_bait"])

    lines = persona["lines"].get(lang, persona["lines"]["hi"])

    return {
        "call_id": call_id,
        "language": lang,
        "persona_id": persona["persona_id"],
        "persona_name": persona["persona_name"],
        "name": persona["persona_name"],
        "persona_age": persona["persona_age"],
        "age": persona["persona_age"],
        "persona_city": persona["persona_city"],
        "city": persona["persona_city"],
        "short_backstory": persona["short_backstory"],
        "persona_lines": list(lines),
        "fake_bait": bait_copy,
        "bait_values": dict(bait_copy),
    }


__all__ = [
    "APPROVED_PERSONAS",
    "APPROVED_BAIT_VALUES",
    "PERSONA_ORDER",
    "SUPPORTED_LANGUAGES",
    "get_rotating_bait",
    "verify_luhn",
    "normalize_language",
    "get_persona_bundle",
]
