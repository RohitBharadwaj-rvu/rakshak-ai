"""
app/voice/cleanup.py - Post-Call LLM Cleanup, Grounding Validator & Summary Generator (T-CLEAN).

Responsibilities:
  - Reconcile and clean up extracted intelligence after the call ends (never on the live call path)
  - Handle digits split across caller turns, mid-call digit corrections ("no, the last digit is seven"),
    speech-to-text slips ("okay axis", "pay t m"), and ungrounded `log_intel` disagreements
  - Cite the exact transcript turn indices for every extracted entity and validate 100% grounding
  - Enforce strict format validation (UPI, IFSC, phone, bank account, PAN, link)
  - Generate a call summary <= 80 words stating verdict and scam_type, referencing only grounded intel
"""

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.rules import (
    APPROVED_BAIT_VALUES,
    BANK_ACCOUNT_PATTERN,
    EMAIL_DOMAINS_TO_EXCLUDE,
    IFSC_PATTERN,
    LINK_PATTERN,
    PAN_PATTERN,
    PHONE_PATTERN,
    UPI_PATTERN,
)
from app.voice.extractor import CALLER_ROLES, extract_entities_from_text
from app.voice.normalizer import DIGIT_WORDS, normalize_spoken_text

logger = logging.getLogger(__name__)

# STT slip normalizations for post-call cleanup
_STT_SLIP_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:okay|ok)\s+axis(?:\s+bank)?\b", re.IGNORECASE), "okaxis"),
    (re.compile(r"\b(?:okay|ok)\s+hdfc(?:\s+bank)?\b", re.IGNORECASE), "okhdfcbank"),
    (re.compile(r"\b(?:okay|ok)\s+icici(?:\s+bank)?\b", re.IGNORECASE), "okicici"),
    (re.compile(r"\b(?:okay|ok)\s+sbi(?:\s+bank)?\b", re.IGNORECASE), "oksbi"),
    (re.compile(r"\bpay\s*t\s*m\b", re.IGNORECASE), "paytm"),
    (re.compile(r"\by\s+b\s+l\b", re.IGNORECASE), "ybl"),
]

# Patterns for mid-call last-digit(s) corrections:
# e.g., "no, the last digit is seven", "sorry last digit is 4", "नहीं आखिरी अंक सात है", "last two digits are 89"
_LAST_DIGIT_CORRECTION_RE = re.compile(
    r"(?:no|sorry|wait|wrong|mistake|correction|अरे|नहीं|गलत|ग़लत|माफ़|सॉरी)[^.!?।]{0,45}?"
    r"(?:last\s+(?:(two|2)\s+)?digit(?:s)?\s+(?:is|are)|आखिरी\s+(?:अंक|नंबर|डिजिट))\s+([A-Za-z0-9\u0900-\u097F\s]+)",
    re.IGNORECASE,
)

# Retraction / replacement markers within or across turns:
# e.g., "9884511111@okaxis... wait no sorry, use 9884567890@paytm"
_RETRACTION_CUE_RE = re.compile(
    r"\b(?:no\s+sorry|wait\s+no|not\s+that\s+one|wrong\s+number|wrong\s+upi|wrong\s+account|"
    r"don't\s+send\s+to|do\s+not\s+use|instead\s+send\s+to|instead\s+use|sorry\s+mistake|"
    r"नहीं\s+sorry|नहीं\s+ग़लत|नहीं\s+गलत|वो\s+गलत\s+है|उसके\s+बदले)\b",
    re.IGNORECASE,
)

# Partial digit chunk pattern (3 to 8 digits) for cross-turn stitching
_DIGIT_CHUNK_RE = re.compile(r"(?<![A-Za-z0-9@._/-])(\d{3,8})(?![A-Za-z0-9@._/-])")
_NON_ACCOUNT_CONTEXT_RE = re.compile(
    r"\b(?:otp|pin|rupees|rupee|rs|inr|thousand|lakh|हज़ार|हजार|लाख|रुपये|रुपए|बजे|am|pm)\b",
    re.IGNORECASE,
)


def _clean_stt_slips(text: str) -> str:
    out = text
    for pat, repl in _STT_SLIP_PATTERNS:
        out = pat.sub(repl, out)
    return normalize_spoken_text(out)


def validate_entity_format(entity_type: str, value: str) -> bool:
    """Strict format check for UPI, IFSC, phone, bank account, PAN, and link (T-CLEAN)."""
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if v.lower() in APPROVED_BAIT_VALUES:
        return False

    if entity_type == "upi_ids":
        m = UPI_PATTERN.fullmatch(v.lower())
        if not m:
            return False
        user_part, domain = v.lower().split("@", 1)
        if ".." in user_part or user_part.startswith((".", "-", "_")) or user_part.endswith((".", "-", "_")):
            return False
        return domain not in EMAIL_DOMAINS_TO_EXCLUDE
    elif entity_type == "phone_numbers":
        return bool(re.fullmatch(r"[6-9]\d{9}", v))
    elif entity_type == "bank_accounts":
        if not re.fullmatch(r"\d{9,18}", v):
            return False
        if len(v) == 10 and v[0] in "6789":
            return False
        return True
    elif entity_type == "ifsc_codes":
        return bool(IFSC_PATTERN.fullmatch(v.upper()))
    elif entity_type == "pan_numbers":
        return bool(PAN_PATTERN.fullmatch(v.upper()))
    elif entity_type == "links":
        return bool(LINK_PATTERN.fullmatch(v))
    return False


def _resolve_correction_digits(raw_tail: str) -> Optional[str]:
    """Convert the trailing word(s) of a last-digit correction into ASCII digits."""
    norm = normalize_spoken_text(raw_tail).strip()
    m = re.match(r"^(\d{1,3})\b", norm)
    if m:
        return m.group(1)
    first_tok = re.split(r"[\s.,!?;:।|]+", raw_tail.strip())[0].lower()
    if first_tok in DIGIT_WORDS:
        return DIGIT_WORDS[first_tok]
    return None


def _apply_turn_text_corrections(norm_text: str) -> Tuple[str, Set[str]]:
    """
    Detect inline self-corrections within a single turn or across adjacent turns:
      1. "50100432891235 ... no, the last digit is 4" -> replaces 50100432891235 with 50100432891234
      2. "old_val ... wait no sorry ... new_val" -> marks old_val as retracted
    Returns (corrected_text, retracted_values).
    """
    retracted: Set[str] = set()
    updated = norm_text

    # 1. Check for "last digit is X" / "आखिरी अंक X है"
    for m in _LAST_DIGIT_CORRECTION_RE.finditer(norm_text):
        replacement_digits = _resolve_correction_digits(m.group(2))
        if not replacement_digits:
            continue
        prefix_text = norm_text[: m.start()]
        num_matches = list(re.finditer(r"\b(\d{9,18})\b", prefix_text))
        if num_matches:
            last_num_match = num_matches[-1]
            orig_num = last_num_match.group(1)
            k = len(replacement_digits)
            if len(orig_num) > k:
                corrected_num = orig_num[:-k] + replacement_digits
                retracted.add(orig_num.lower())
                updated = updated.replace(orig_num, corrected_num)

    # 2. Check for retraction cue between two entities in the same turn
    cue_match = _RETRACTION_CUE_RE.search(updated)
    if cue_match:
        before_cue = updated[: cue_match.start()]
        after_cue = updated[cue_match.end() :]
        before_ent = extract_entities_from_text(before_cue)
        after_ent = extract_entities_from_text(after_cue)
        for bucket in ("upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"):
            if before_ent[bucket] and after_ent[bucket]:
                for old_v in before_ent[bucket]:
                    if old_v.lower() not in {x.lower() for x in after_ent[bucket]}:
                        retracted.add(old_v.lower())

    return updated, retracted


def verify_value_grounded(
    entity_type: str,
    value: str,
    cited_turns: List[int],
    transcript: List[Dict[str, Any]],
) -> bool:
    """
    Grounding validator (T-CLEAN):
    Verifies that:
      1. `cited_turns` is non-empty and every index points to a caller turn in `transcript`
      2. When those cited caller turns are normalized (including split-turn stitching and
         spoken last-digit corrections), `value` is demonstrably present in them
      3. `value` passes `validate_entity_format(entity_type, value)`
    """
    if not cited_turns or not validate_entity_format(entity_type, value):
        return False

    norm_pieces: List[str] = []
    for idx in cited_turns:
        if not isinstance(idx, int) or idx < 0 or idx >= len(transcript):
            return False
        turn = transcript[idx]
        role = str(turn.get("role") or turn.get("sender") or "").lower().strip()
        if role not in CALLER_ROLES:
            return False
        raw = str(turn.get("content") or turn.get("text") or "")
        norm_pieces.append(_clean_stt_slips(raw))

    combined = " ".join(norm_pieces)
    corrected_combined, _ = _apply_turn_text_corrections(combined)

    # Also build a stitched version where split digit chunks across cited turns are joined
    chunks = _DIGIT_CHUNK_RE.findall(corrected_combined)
    stitched_str = "".join(chunks) if len(chunks) >= 2 else ""

    target = value.lower().strip()
    if target in corrected_combined.lower():
        return True
    if stitched_str and target == stitched_str.lower():
        return True
    return False


def _infer_scam_type(transcript: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> str:
    meta = metadata or {}
    if meta.get("simulated_scam_type"):
        return str(meta["simulated_scam_type"])
    if meta.get("scenario"):
        return str(meta["scenario"])

    full_text = " ".join(
        str(t.get("content") or t.get("text") or "").lower()
        for t in transcript
        if str(t.get("role") or t.get("sender") or "").lower() in CALLER_ROLES
    )
    if any(w in full_text for w in ("digital arrest", "डिजिटल अरेस्ट", "cbi", "warrant", "narcotics")):
        return "digital_arrest"
    if any(w in full_text for w in ("electricity", "बिजली", "power cut", "meter")):
        return "electricity_bill_scam"
    if any(w in full_text for w in ("kyc", "केवाईसी", "pan card", "account blocked", "खाता ब्लॉक")):
        return "bank_kyc"
    if any(w in full_text for w in ("customs", "parcel", "पार्सल", "contraband")):
        return "customs_parcel"
    if any(w in full_text for w in ("challan", "traffic", "चालान")):
        return "traffic_challan"
    if any(w in full_text for w in ("part time", "job", "telegram", "नौकरी")):
        return "job_scam"
    return "general_telephony"


def _build_grounded_summary(
    verdict: str,
    scam_type: str,
    extracted_intel: Dict[str, Any],
) -> str:
    """
    Build a concise call summary (strictly <= 80 words) that states the verdict and scam_type,
    and includes ONLY entities present in `extracted_intel` (zero ungrounded details).
    """
    if verdict == "genuine":
        scam_label = scam_type if scam_type != "general_telephony" else "none"
    else:
        scam_label = scam_type

    sentences = [f"Call verdict is {verdict} with scam_type {scam_label}."]

    intel_parts = []
    if extracted_intel.get("upi_ids"):
        intel_parts.append(f"UPI IDs: {', '.join(extracted_intel['upi_ids'])}")
    if extracted_intel.get("bank_accounts"):
        intel_parts.append(f"bank accounts: {', '.join(extracted_intel['bank_accounts'])}")
    if extracted_intel.get("ifsc_codes"):
        intel_parts.append(f"IFSC codes: {', '.join(extracted_intel['ifsc_codes'])}")
    if extracted_intel.get("phone_numbers"):
        intel_parts.append(f"phone numbers: {', '.join(extracted_intel['phone_numbers'])}")
    if extracted_intel.get("pan_numbers"):
        intel_parts.append(f"PAN numbers: {', '.join(extracted_intel['pan_numbers'])}")
    if extracted_intel.get("links"):
        intel_parts.append(f"links: {', '.join(extracted_intel['links'])}")

    if intel_parts:
        sentences.append("Captured scammer intelligence includes " + "; ".join(intel_parts) + ".")
    else:
        sentences.append("No financial or contact intelligence entities were captured during the call.")

    summary = " ".join(sentences)
    words = summary.split()
    if len(words) > 80:
        summary = " ".join(words[:80])
    return summary


def cleanup_call_intel(
    transcript: List[Dict[str, Any]],
    verdict: str = "scam",
    mid_call_logs: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Post-call intelligence cleanup & summary pipeline (T-CLEAN).
    Never runs on the live mid-call path.
    Returns:
      {
        "extracted_intel": {
          "upi_ids": [...],
          "phone_numbers": [...],
          "bank_accounts": [...],
          "ifsc_codes": [...],
          "pan_numbers": [...],
          "links": [...],
          "entity_counts": {...},
          "mid_call_logs": [...],
          "citations": { "<value>": [turn_idx, ...] }
        },
        "summary": "...",
        "scam_type": "..."
      }
    """
    entity_keys = ["upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"]
    candidates: Dict[str, List[str]] = {k: [] for k in entity_keys}
    citations: Dict[str, List[int]] = {}
    entity_counts: Dict[str, int] = {}
    retracted_values: Set[str] = set()

    caller_turns: List[Tuple[int, str, str]] = []  # (turn_idx, raw_text, norm_text)
    for idx, turn in enumerate(transcript or []):
        role = str(turn.get("role") or turn.get("sender") or "").lower().strip()
        if role not in CALLER_ROLES:
            continue
        raw = str(turn.get("content") or turn.get("text") or "")
        if not raw:
            continue
        norm = _clean_stt_slips(raw)
        caller_turns.append((idx, raw, norm))

    def _add_candidate(bucket: str, val: str, turn_indices: List[int]) -> None:
        canon = val.upper() if bucket in ("ifsc_codes", "pan_numbers") else (
            val.lower() if bucket == "upi_ids" else val
        )
        if not validate_entity_format(bucket, canon):
            return
        if canon not in candidates[bucket]:
            candidates[bucket].append(canon)
        entity_counts[canon] = entity_counts.get(canon, 0) + 1
        existing_cites = citations.get(canon, [])
        for t_idx in turn_indices:
            if t_idx not in existing_cites:
                existing_cites.append(t_idx)
        citations[canon] = existing_cites

    # Pass 1: Per-turn extraction + inline corrections
    for pos, (turn_idx, _raw, norm_text) in enumerate(caller_turns):
        corrected_text, turn_retracted = _apply_turn_text_corrections(norm_text)
        retracted_values |= turn_retracted

        # Also check if this turn is a correction of the immediately preceding caller turn!
        if pos > 0:
            prev_idx, _prev_raw, prev_norm = caller_turns[pos - 1]
            if _LAST_DIGIT_CORRECTION_RE.search(norm_text) or _RETRACTION_CUE_RE.search(norm_text):
                pair_corrected, pair_retracted = _apply_turn_text_corrections(f"{prev_norm} {norm_text}")
                retracted_values |= pair_retracted
                pair_ents = extract_entities_from_text(pair_corrected)
                for k in entity_keys:
                    for v in pair_ents[k]:
                        if v.lower() not in pair_retracted:
                            _add_candidate(k, v, [prev_idx, turn_idx])

        turn_ents = extract_entities_from_text(corrected_text)
        for k in entity_keys:
            for v in turn_ents[k]:
                if v.lower() not in retracted_values:
                    _add_candidate(k, v, [turn_idx])

    # Pass 2: Cross-turn split digit stitching across adjacent caller turns
    for pos in range(len(caller_turns) - 1):
        idx1, _raw1, norm1 = caller_turns[pos]
        idx2, _raw2, norm2 = caller_turns[pos + 1]

        # Skip if either turn already yielded a full phone/account or has retraction cues
        if _RETRACTION_CUE_RE.search(norm1) or _RETRACTION_CUE_RE.search(norm2):
            continue
        if _NON_ACCOUNT_CONTEXT_RE.search(norm1) or _NON_ACCOUNT_CONTEXT_RE.search(norm2):
            continue

        e1 = extract_entities_from_text(norm1)
        e2 = extract_entities_from_text(norm2)
        if e1["phone_numbers"] or e1["bank_accounts"] or e2["phone_numbers"] or e2["bank_accounts"]:
            continue

        c1 = _DIGIT_CHUNK_RE.findall(norm1)
        c2 = _DIGIT_CHUNK_RE.findall(norm2)
        if len(c1) == 1 and len(c2) == 1:
            stitched = c1[0] + c2[0]
            if len(stitched) == 10 and stitched[0] in "6789":
                _add_candidate("phone_numbers", stitched, [idx1, idx2])
            elif 9 <= len(stitched) <= 18 and not (len(stitched) == 10 and stitched[0] in "6789"):
                _add_candidate("bank_accounts", stitched, [idx1, idx2])

    # Pass 3: Remove any retracted values and run strict grounding verification on every candidate
    grounded_intel: Dict[str, Any] = {k: [] for k in entity_keys}
    grounded_citations: Dict[str, List[int]] = {}
    grounded_counts: Dict[str, int] = {}

    for k in entity_keys:
        for val in candidates[k]:
            if val.lower() in retracted_values:
                continue
            cites = citations.get(val, [])
            if verify_value_grounded(k, val, cites, transcript):
                grounded_intel[k].append(val)
                grounded_citations[val] = cites
                grounded_counts[val] = entity_counts.get(val, 1)

    # Note: mid_call_logs are preserved for audit in `mid_call_logs`, but ungrounded mid_call_logs
    # are NEVER injected into grounded_intel buckets if they disagree with the transcript!
    grounded_intel["entity_counts"] = grounded_counts
    grounded_intel["mid_call_logs"] = list(mid_call_logs or [])
    grounded_intel["citations"] = grounded_citations

    scam_type = _infer_scam_type(transcript, metadata=metadata)
    summary = _build_grounded_summary(
        verdict=verdict,
        scam_type=scam_type,
        extracted_intel=grounded_intel,
    )

    return {
        "extracted_intel": grounded_intel,
        "summary": summary,
        "scam_type": scam_type,
    }
