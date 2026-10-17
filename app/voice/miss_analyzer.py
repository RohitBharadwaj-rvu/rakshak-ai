"""
app/voice/miss_analyzer.py - Sprint 4 STT Extraction-Miss & Garbled-Phrase Analyzer (Lane B).

Responsibilities:
  - Compare finalized CallRecords (or fixture runs) against expected planted intelligence
  - Identify any missed UPI IDs, bank accounts, IFSC codes, phone numbers, PANs, or links
  - Inspect `mid_call_logs` with `unparseable=True` and raw caller turns to pinpoint which
    digits or phrases speech-to-text (STT) garbled
  - Produce a structured diagnostic report for Sprint 4 analysis
"""

import re
from typing import Any, Dict, List, Optional

from app.voice.extractor import CALLER_ROLES
from app.voice.normalizer import normalize_spoken_text

_PLANTED_KEY_MAP = {
    "upi_id": "upi_ids",
    "upi_ids": "upi_ids",
    "phone_number": "phone_numbers",
    "phone_numbers": "phone_numbers",
    "account_number": "bank_accounts",
    "bank_accounts": "bank_accounts",
    "ifsc_code": "ifsc_codes",
    "ifsc_codes": "ifsc_codes",
    "pan_number": "pan_numbers",
    "pan_numbers": "pan_numbers",
    "link": "links",
    "links": "links",
}

_GARBLE_PATTERNS = [
    ("spaced_handle", re.compile(r"\b(?:okay|ok)\s+(?:axis|hdfc|icici|sbi)\b|\bpay\s+t\s+m\b|\by\s+b\s+l\b", re.I)),
    ("spoken_at_or_dot", re.compile(r"\b(?:at\s+the\s+rate|ऐट\s+द\s+रेट|dot|डॉट)\b", re.I)),
    ("repetitions_double_triple", re.compile(r"\b(?:double|triple|डबल|ट्रिपल)\b", re.I)),
    ("hindi_number_words", re.compile(r"(?:शून्य|एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|नौ|दस|बीस|पचास)")),
    ("mid_call_self_correction", re.compile(r"\b(?:sorry|wait|wrong|mistake|last\s+digit|आखिरी\s+अंक|नहीं)\b", re.I)),
]


def _diagnose_garble_causes(transcript: List[Dict[str, Any]]) -> List[str]:
    caller_text = " ".join(
        str(t.get("content") or t.get("text") or "")
        for t in (transcript or [])
        if str(t.get("role") or t.get("sender") or "").lower().strip() in CALLER_ROLES
    )
    causes: List[str] = []
    for label, pat in _GARBLE_PATTERNS:
        if pat.search(caller_text):
            causes.append(label)
    return causes


def analyze_call_extraction(
    record: Dict[str, Any],
    planted_intel: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analyze a single CallRecord against optional `planted_intel` ground truth.
    Returns hit/miss breakdown, unparseable mid-call logs, and STT garble diagnostics.
    """
    call_id = str(record.get("call_id") or "unknown")
    intel = record.get("extracted_intel") or {}
    transcript = record.get("transcript") or []
    planted = planted_intel or {}

    expected_by_bucket: Dict[str, List[str]] = {}
    for raw_k, raw_v in planted.items():
        bucket = _PLANTED_KEY_MAP.get(raw_k)
        if not bucket or not raw_v:
            continue
        vals = [raw_v] if isinstance(raw_v, str) else list(raw_v)
        expected_by_bucket.setdefault(bucket, []).extend(str(x).strip() for x in vals if str(x).strip())

    hits: List[Dict[str, str]] = []
    misses: List[Dict[str, Any]] = []

    for bucket, expected_vals in expected_by_bucket.items():
        actual_low = {str(x).lower().strip() for x in (intel.get(bucket) or [])}
        for exp in expected_vals:
            if exp.lower() in actual_low:
                hits.append({"bucket": bucket, "expected": exp})
            else:
                caller_raw = " | ".join(
                    str(t.get("content") or t.get("text") or "")
                    for t in transcript
                    if str(t.get("role") or t.get("sender") or "").lower().strip() in CALLER_ROLES
                )
                misses.append(
                    {
                        "call_id": call_id,
                        "bucket": bucket,
                        "expected": exp,
                        "actual_in_bucket": list(intel.get(bucket) or []),
                        "stt_garble_patterns": _diagnose_garble_causes(transcript),
                        "caller_utterances_raw": caller_raw,
                        "caller_utterances_normalized": normalize_spoken_text(caller_raw),
                    }
                )

    unparseable_logs = [
        log_item
        for log_item in (intel.get("mid_call_logs") or [])
        if log_item.get("unparseable") is True
    ]

    return {
        "call_id": call_id,
        "expected_count": len(hits) + len(misses),
        "hit_count": len(hits),
        "miss_count": len(misses),
        "hits": hits,
        "misses": misses,
        "unparseable_mid_call_logs": unparseable_logs,
        "stt_phenomena_present": _diagnose_garble_causes(transcript),
    }


def analyze_corpus_extraction_misses(
    records_with_planted: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyze a batch of `{"record": CallRecord, "planted_intel": {...}}` items and
    compute overall Sprint 4 extraction accuracy and STT miss diagnostics.
    """
    per_call: List[Dict[str, Any]] = []
    all_misses: List[Dict[str, Any]] = []
    all_unparseable: List[Dict[str, Any]] = []
    total_expected = 0
    total_hits = 0
    calls_with_planted = 0
    calls_capturing_at_least_one = 0

    for item in records_with_planted:
        rec = item.get("record") or item
        planted = item.get("planted_intel") or (rec.get("metadata") or {}).get("planted_intel") or {}
        res = analyze_call_extraction(rec, planted_intel=planted)
        per_call.append(res)
        total_expected += res["expected_count"]
        total_hits += res["hit_count"]
        if res["expected_count"] > 0:
            calls_with_planted += 1
            if res["hit_count"] > 0:
                calls_capturing_at_least_one += 1
        all_misses.extend(res["misses"])
        for u in res["unparseable_mid_call_logs"]:
            all_unparseable.append({"call_id": res["call_id"], **u})

    entity_recall_pct = (total_hits / total_expected * 100.0) if total_expected > 0 else 100.0
    call_level_accuracy_pct = (
        (calls_capturing_at_least_one / calls_with_planted * 100.0)
        if calls_with_planted > 0
        else 100.0
    )

    return {
        "summary": {
            "total_calls_analyzed": len(records_with_planted),
            "calls_with_planted_intel": calls_with_planted,
            "calls_capturing_planted_intel": calls_capturing_at_least_one,
            "call_level_extraction_accuracy_pct": round(call_level_accuracy_pct, 2),
            "total_expected_entities": total_expected,
            "total_captured_entities": total_hits,
            "entity_level_recall_pct": round(entity_recall_pct, 2),
            "total_misses": len(all_misses),
            "total_unparseable_mid_call_logs": len(all_unparseable),
        },
        "misses": all_misses,
        "unparseable_mid_call_logs": all_unparseable,
        "per_call": per_call,
    }
