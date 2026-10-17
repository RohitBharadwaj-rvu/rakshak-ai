"""
app/agent/nodes/reflection.py - Post-Call Reflection Node (T-POST).

Analyzes a completed call transcript after the CallRecord has been saved:
  - Evaluates scammer pressure tactics (urgency, authority impersonation, payment demand, OTP fishing)
  - Measures conversation engagement (caller turns, agent turns, honeypot engagement quality)
  - Produces structured reflection notes without ever blocking the live call or webhook response
"""

import logging
from typing import Any, Dict, List

from app.voice.extractor import CALLER_ROLES

logger = logging.getLogger(__name__)

_TACTIC_KEYWORDS: Dict[str, List[str]] = {
    "authority_impersonation": [
        "cbi", "police", "reserve bank", "rbi", "customs", "officer", "inspector",
        "court", "warrant", "cyber crime", "पुलिस", "सीबीआई", "अधिकारी", "कस्टम", "कोर्ट",
    ],
    "urgency_coercion": [
        "immediately", "right now", "within 10 minutes", "arrest", "digital arrest",
        "disconnect", "blocked", "turant", "abhi", "तुरंत", "अभी", "गिरफ्तार", "डिजिटल अरेस्ट", "ब्लॉक",
    ],
    "financial_demand": [
        "upi", "transfer", "send money", "deposit", "penalty", "fine", "fee",
        "account", "ifsc", "पैसे", "भेजो", "जमा", "जुर्माना", "खाता",
    ],
    "credential_fishing": [
        "otp", "pin", "cvv", "password", "anydesk", "teamviewer", "screen share",
        "ओटीपी", "पिन", "पासवर्ड",
    ],
}


def run_post_call_reflection(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a finalized CallRecord and return structured post-call reflection metadata.
    Runs strictly post-call (T-POST).
    """
    call_id = str(record.get("call_id") or "unknown")
    transcript: List[Dict[str, Any]] = record.get("transcript") or []
    verdict = str(record.get("verdict") or "unsure")
    intel = record.get("extracted_intel") or {}

    caller_turns = [
        t for t in transcript
        if str(t.get("role") or t.get("sender") or "").lower().strip() in CALLER_ROLES
    ]
    agent_turns = [
        t for t in transcript
        if str(t.get("role") or t.get("sender") or "").lower().strip() not in CALLER_ROLES
    ]

    caller_text = " ".join(
        str(t.get("content") or t.get("text") or "").lower() for t in caller_turns
    )

    tactics_detected: List[str] = []
    for tactic, keywords in _TACTIC_KEYWORDS.items():
        if any(kw in caller_text for kw in keywords):
            tactics_detected.append(tactic)

    total_intel_count = sum(
        len(intel.get(k) or [])
        for k in ("upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links")
    )

    if verdict == "scam":
        if total_intel_count > 0:
            outcome = "high_value_intel_captured"
        elif len(caller_turns) >= 2:
            outcome = "scammer_stalled_no_payment_id"
        else:
            outcome = "early_scam_drop"
    elif verdict == "genuine":
        outcome = "genuine_caller_routed"
    else:
        outcome = "screened_unsure"

    reflection = {
        "call_id": call_id,
        "caller_turn_count": len(caller_turns),
        "agent_turn_count": len(agent_turns),
        "total_turns": len(transcript),
        "tactics_detected": tactics_detected,
        "total_entities_captured": total_intel_count,
        "engagement_outcome": outcome,
    }
    logger.info(
        "Post-call reflection completed call_id=%s outcome=%s tactics=%s",
        call_id,
        outcome,
        tactics_detected,
    )
    return reflection


def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph-compatible wrapper around `run_post_call_reflection`."""
    reflection = run_post_call_reflection(state)
    return {**state, "reflection": reflection}
