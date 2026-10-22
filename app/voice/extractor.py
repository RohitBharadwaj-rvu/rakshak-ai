"""
app/voice/extractor.py - Rule-Based Transcript Intelligence Extractor (T-EXT).

Extracts UPI IDs, Indian mobile numbers, bank account numbers, IFSC codes,
PAN numbers, and phishing links from caller turns only.
Enforces:
  - Speaker attribution: never extracts from assistant/agent turns
  - Bait filtering: never extracts values from APPROVED_BAIT_VALUES
  - Deduplication with exact occurrence counts in `entity_counts`
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
from app.voice.normalizer import normalize_spoken_text

CALLER_ROLES = {"user", "caller", "scammer"}


def _clean_trailing_punct(val: str) -> str:
    return val.rstrip(".,!?;:)]}'\"।|").lstrip("([{'\"")


def _is_bait(val: str, extra_bait: Set[str]) -> bool:
    low = val.lower().strip()
    return low in APPROVED_BAIT_VALUES or low in extra_bait


def extract_entities_from_text(
    raw_text: str,
    extra_bait: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    """
    Normalize a single caller utterance and return all extracted entity occurrences
    (with duplicates preserved so caller repeat counts can be tallied).
    """
    bait_set = {b.lower().strip() for b in (extra_bait or set())}
    norm_text = normalize_spoken_text(raw_text)

    upis: List[str] = []
    phones: List[str] = []
    accounts: List[str] = []
    ifscs: List[str] = []
    pans: List[str] = []
    links: List[str] = []

    # 1. Links (extract first so URLs aren't misread as handles)
    for m in LINK_PATTERN.findall(norm_text):
        cleaned = _clean_trailing_punct(m)
        if cleaned and not _is_bait(cleaned, bait_set):
            links.append(cleaned)

    # 2. UPI IDs
    for m in UPI_PATTERN.findall(norm_text):
        cleaned = _clean_trailing_punct(m).lower()
        if "@" not in cleaned:
            continue
        user_part, domain = cleaned.split("@", 1)
        if (
            not user_part
            or ".." in user_part
            or user_part.startswith((".", "-", "_"))
            or user_part.endswith((".", "-", "_"))
        ):
            continue
        if domain in EMAIL_DOMAINS_TO_EXCLUDE:
            continue
        if not _is_bait(cleaned, bait_set):
            upis.append(cleaned)

    # 3. Phone Numbers (10 digits starting with 6-9)
    for m in PHONE_PATTERN.findall(norm_text):
        digits = re.sub(r"[\s-]", "", m)
        if len(digits) == 10 and digits[0] in "6789":
            if not _is_bait(digits, bait_set):
                phones.append(digits)

    # 4. Bank Accounts (9 to 18 digits, excluding mobile numbers)
    phone_set = set(phones)
    for m in BANK_ACCOUNT_PATTERN.findall(norm_text):
        digits = m.strip()
        if len(digits) < 9 or len(digits) > 18:
            continue
        # Reject 10-digit Indian mobile numbers (6-9 start)
        if len(digits) == 10 and digits[0] in "6789":
            continue
        # Reject 11-digit 0-prefixed mobile numbers
        if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
            continue
        # Reject 12-digit 91-prefixed mobile numbers
        if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
            continue
        if digits[-10:] in phone_set and len(digits) <= 12:
            continue
        if not _is_bait(digits, bait_set):
            accounts.append(digits)

    # 5. IFSC Codes (4 letters + 0 + 6 alphanumeric)
    for m in IFSC_PATTERN.findall(norm_text):
        code = m.upper().strip()
        if not _is_bait(code, bait_set):
            ifscs.append(code)

    # 6. PAN Numbers (5 letters + 4 digits + 1 letter)
    for m in PAN_PATTERN.findall(norm_text):
        pan = m.upper().strip()
        if not _is_bait(pan, bait_set):
            pans.append(pan)

    return {
        "upi_ids": upis,
        "phone_numbers": phones,
        "bank_accounts": accounts,
        "ifsc_codes": ifscs,
        "pan_numbers": pans,
        "links": links,
    }


def extract_from_transcript(
    transcript: Iterable[Dict[str, Any]],
    extra_bait: Optional[Set[str]] = None,
    mid_call_logs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Extract all scammer intelligence from a conversation transcript, strictly ignoring
    assistant/agent turns and approved bait values, and merging any mid-call `log_intel`
    captures.
    """
    bait_set = {b.lower().strip() for b in (extra_bait or set())}

    upi_list: List[str] = []
    phone_list: List[str] = []
    account_list: List[str] = []
    ifsc_list: List[str] = []
    pan_list: List[str] = []
    link_list: List[str] = []
    entity_counts: Dict[str, int] = {}

    def _record(target_list: List[str], val: str, count_inc: int = 1) -> None:
        if _is_bait(val, bait_set):
            return
        if val not in target_list:
            target_list.append(val)
        entity_counts[val] = entity_counts.get(val, 0) + count_inc

    caller_norm_turns: List[str] = []
    for turn in transcript or []:
        role = str(turn.get("role") or turn.get("sender") or "").lower().strip()
        if role not in CALLER_ROLES:
            continue
        text = str(turn.get("content") or turn.get("text") or "")
        if not text:
            continue

        caller_norm_turns.append(normalize_spoken_text(text))
        turn_entities = extract_entities_from_text(text, extra_bait=bait_set)
        for u in turn_entities["upi_ids"]:
            _record(upi_list, u, 1)
        for p in turn_entities["phone_numbers"]:
            _record(phone_list, p, 1)
        for a in turn_entities["bank_accounts"]:
            _record(account_list, a, 1)
        for i in turn_entities["ifsc_codes"]:
            _record(ifsc_list, i, 1)
        for pan in turn_entities["pan_numbers"]:
            _record(pan_list, pan, 1)
        for lnk in turn_entities["links"]:
            _record(link_list, lnk, 1)

    # Check adjacent caller turns for split UPI (<user_part> on turn k, <provider> on turn k+1)
    known_providers = {"ybl", "okaxis", "oksbi", "okhdfcbank", "okicici", "paytm", "ibl", "axl", "upi", "apl"}
    upi_user_re = re.compile(r"([a-z0-9]+(?:[._-][a-z0-9]+)+|[a-z]{3,20}\d{1,6})$", re.IGNORECASE)
    for idx in range(len(caller_norm_turns) - 1):
        t1 = _clean_trailing_punct(caller_norm_turns[idx].strip()).lower()
        t2 = _clean_trailing_punct(caller_norm_turns[idx + 1].strip()).lower().lstrip("@")
        if t2 in known_providers and "@" not in t1:
            m_user = upi_user_re.search(t1)
            if m_user:
                stitched_upi = f"{m_user.group(1).lower()}@{t2}"
                if UPI_PATTERN.fullmatch(stitched_upi):
                    _record(upi_list, stitched_upi, 1)

    # Merge mid-call log_intel captures if present and parseable
    cleaned_mid_logs: List[Dict[str, Any]] = []
    for item in mid_call_logs or []:
        itype = str(item.get("type") or item.get("kind") or "other").lower()
        val_heard = str(item.get("value_as_heard") or item.get("value_raw") or "")
        norm_val, unparseable = normalize_and_validate_single_intel(itype, val_heard)
        if unparseable and item.get("normalized_value") and not item.get("unparseable"):
            # log_intel already validated this (e.g. via the agent's value_normalized hint).
            norm_val, unparseable = str(item["normalized_value"]), False
        # Keep every Addition 1 field (elicitation, quote, turn_index, times_logged, ...) so
        # evidence packets built after the webhook still see them.
        log_entry = dict(item)
        log_entry.update(
            {
                "type": itype,
                "kind": itype,
                "value_as_heard": val_heard,
                "value_raw": val_heard,
                "normalized_value": norm_val,
                "value_normalized": norm_val,
                "unparseable": unparseable,
            }
        )
        cleaned_mid_logs.append(log_entry)
        if not unparseable and norm_val and not item.get("is_bait") and not _is_bait(norm_val, bait_set):
            if itype == "upi" and norm_val not in upi_list:
                _record(upi_list, norm_val, 1)
            elif itype == "phone" and norm_val not in phone_list:
                _record(phone_list, norm_val, 1)
            elif itype == "account" and norm_val not in account_list:
                _record(account_list, norm_val, 1)
            elif itype == "ifsc" and norm_val not in ifsc_list:
                _record(ifsc_list, norm_val, 1)
            elif itype == "pan" and norm_val not in pan_list:
                _record(pan_list, norm_val, 1)
            elif itype == "link" and norm_val not in link_list:
                _record(link_list, norm_val, 1)

    return {
        "upi_ids": upi_list,
        "phone_numbers": phone_list,
        "bank_accounts": account_list,
        "ifsc_codes": ifsc_list,
        "pan_numbers": pan_list,
        "links": link_list,
        "entity_counts": entity_counts,
        "mid_call_logs": cleaned_mid_logs,
    }


def normalize_and_validate_single_intel(intel_type: str, value_as_heard: str) -> Tuple[str, bool]:
    """
    Normalize a single mid-call `log_intel` capture and check whether it forms a valid
    entity of `intel_type`. Returns `(normalized_value, unparseable)`.
    Never raises; unparseable values are kept with `unparseable=True`.
    """
    raw = (value_as_heard or "").strip()
    if not raw:
        return "", True

    norm = normalize_spoken_text(raw).strip()
    extracted = extract_entities_from_text(raw)
    t = (intel_type or "other").lower().strip()

    if t == "upi":
        if extracted["upi_ids"]:
            return extracted["upi_ids"][0], False
        return norm, True
    elif t == "phone":
        if extracted["phone_numbers"]:
            return extracted["phone_numbers"][0], False
        return norm, True
    elif t == "account":
        if extracted["bank_accounts"]:
            return extracted["bank_accounts"][0], False
        return norm, True
    elif t == "ifsc":
        if extracted["ifsc_codes"]:
            return extracted["ifsc_codes"][0], False
        return norm.upper(), True
    elif t == "pan":
        if extracted["pan_numbers"]:
            return extracted["pan_numbers"][0], False
        return norm.upper(), True
    elif t == "link":
        if extracted["links"]:
            return extracted["links"][0], False
        return norm, True
    else:
        return norm, False
