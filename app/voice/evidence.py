"""
app/voice/evidence.py - Citizen Telecom Fraud Evidence Packets (Addition 2).

Generates standardized citizen reporting packets for:
  1. DoT Sanchar Saathi / Chakshu Portal (Citizen Fraud Communication Reporting)
  2. National Cybercrime Reporting Portal / Bank Suspect Reports
Includes SHA-256 evidence integrity hashing.
"""

import hashlib
import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.voice.report import generate_1930_report

logger = logging.getLogger(__name__)

# ==============================================================================
# 4. CHAKSHU CATEGORY MAPPING & TEMPLATE
# ==============================================================================
# TODO: verify current categories on sancharsaathi.gov.in before demo
CHAKSHU_CATEGORY_MAPPING: Dict[str, str] = {
    "digital_arrest": "Digital Arrest / Impersonation of Police or Law Enforcement",
    "police": "Impersonation of Police / Government Official",
    "customs": "Customs / Narcotics / Parcel Seizure",
    "kyc": "Bank Account / KYC / SIM Suspension",
    "bank": "Bank / Financial Institution Impersonation",
    "electricity": "Electricity / Utility Disconnection Threat",
    "courier": "Courier / Delivery Impersonation / OTP Extortion",
    "job": "Part-Time Job / Task Advance Fraud",
    "lottery": "Lottery / Prize / KBC Fraud",
    "relative": "Relative / Friend Emergency Impersonation",
    "loan": "Instant Loan / Harassment Fraud",
    "general": "Suspected Financial / Impersonation Fraud",
}

CHAKSHU_DESCRIPTION_TEMPLATE = (
    "Suspected scam call intercepted by GuardianLine screening. "
    "Call Reference ID: {call_id}. "
    "Suspect Caller Number: {caller_number}. "
    "Duration: {duration_s} seconds. "
    "Verdict: {verdict}. "
    "Extracted Identifiers: {identifiers_summary}. "
    "Incident Summary: {summary}"
)


# ==============================================================================
# 1. INTEGRITY HASHING (CANONICAL TRANSCRIPT & RECORDING BYTES)
# ==============================================================================

def compute_canonical_transcript_hash(transcript: Any) -> str:
    """
    Computes SHA-256 hash over canonical JSON (sorted keys, compact separators, UTF-8).
    """
    if isinstance(transcript, str):
        try:
            parsed = json.loads(transcript)
            canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            canonical = transcript.strip()
    elif isinstance(transcript, (list, dict)):
        canonical = json.dumps(transcript, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        canonical = str(transcript or "").strip()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_recording_bytes_hash(
    recording_url: Optional[str],
    timeout: float = 10.0,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Downloads recording bytes if URL exists (10s timeout) and computes SHA-256 over raw bytes.
    Returns (hash_sha256, failure_reason).
    If no URL exists, returns (None, "no_recording_url").
    """
    if not recording_url or not str(recording_url).strip():
        return None, "no_recording_url"
    url = str(recording_url).strip()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "GuardianLine/1.0 (Evidence-Verifier)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return hashlib.sha256(data).hexdigest(), None
    except Exception as exc:
        logger.warning("Failed to fetch recording bytes from %s: %s", url, exc)
        return None, f"fetch_failed: {type(exc).__name__}"


def compute_evidence_hash(transcript: Any, recording_url: Optional[str], caller_number: str) -> str:
    """Computes a composite SHA-256 integrity hash over call evidence components."""
    t_hash = compute_canonical_transcript_hash(transcript)
    hasher = hashlib.sha256()
    hasher.update((caller_number or "").strip().encode("utf-8"))
    hasher.update(b"|")
    hasher.update((recording_url or "").strip().encode("utf-8"))
    hasher.update(b"|")
    hasher.update(t_hash.encode("utf-8"))
    return hasher.hexdigest()


# ==============================================================================
# DATA MODELS
# ==============================================================================

class SuspectIdentifier(BaseModel):
    kind: str = Field(description="upi, phone, account, ifsc, or link")
    value_normalized: str = Field(description="Normalized suspect identifier value")
    value_raw: Optional[str] = Field(default=None, description="Raw value as spoken or logged")
    seconds_from_start: Optional[float] = Field(default=None, description="Offset in seconds when heard")
    quote: Optional[str] = Field(default=None, description="Spoken context quote (<=120 chars)")
    elicitation: Optional[str] = Field(default=None, description="Elicitation tactic used")
    status: str = Field(default="suspected", description="Suspect status")


class ChakshuPacket(BaseModel):
    version: str = "1.0"
    portal: str = "DoT Sanchar Saathi (Chakshu)"
    call_id: str
    caller_number: str
    category: str
    incident_timestamp: str
    duration_seconds: int
    suspect_identifiers: List[SuspectIdentifier]
    evidence_summary: str
    money_lost: bool = False
    evidence_hash_sha256: str
    evidence_status: str = "draft"
    verification_status: str = "VERIFIED"


class ReportSuspectPacket(BaseModel):
    portal: str = "Report Suspect / Financial Intermediary"
    status: str = "suspected"
    kind: str
    value_normalized: str
    value_raw: str
    associated_call_id: str
    caller_phone: str
    context: str
    evidence_hash_sha256: str
    seconds_from_start: Optional[float] = None
    quote: Optional[str] = None
    elicitation: Optional[str] = None

    @property
    def identifier_type(self) -> str:
        return self.kind

    def to_dict(self) -> Dict[str, Any]:
        """Serialize omitting missing / None fields so older records do not invent values."""
        if hasattr(self, "model_dump"):
            return self.model_dump(exclude_none=True)
        return {k: v for k, v in self.dict().items() if v is not None}


# ==============================================================================
# PACKET BUILDERS
# ==============================================================================

def _get_parent_personal_data(call_record: Dict[str, Any]) -> Tuple[set, set, set]:
    meta = call_record.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    phones = {
        str(p).strip()
        for p in [
            call_record.get("user_number"),
            call_record.get("callee_number"),
            call_record.get("parent_phone"),
            call_record.get("victim_phone"),
            call_record.get("own_number"),
            meta.get("user_number"),
            meta.get("parent_phone"),
            meta.get("own_number"),
            meta.get("callee_number"),
            meta.get("victim_phone"),
        ]
        if p and str(p).strip()
    }
    names = {
        str(n).strip()
        for n in [
            call_record.get("parent_name"),
            call_record.get("user_name"),
            call_record.get("victim_name"),
            meta.get("parent_name"),
            meta.get("user_name"),
            meta.get("victim_name"),
        ]
        if n and str(n).strip()
    }
    addresses = {
        str(a).strip()
        for a in [
            call_record.get("parent_address"),
            call_record.get("user_address"),
            call_record.get("address"),
            meta.get("parent_address"),
            meta.get("user_address"),
            meta.get("address"),
        ]
        if a and str(a).strip()
    }
    return phones, names, addresses


def _extract_suspect_identifiers(call_record: Dict[str, Any]) -> List[SuspectIdentifier]:
    """
    Extracts suspect identifiers with provenance from mid_call_logs or extracted_intel.
    Omit missing fields from older records; never invent values.
    Filters out parent personal data (phone, name, address) to safeguard privacy.
    """
    caller_num = str(call_record.get("caller_number") or "").strip()
    parent_phones, parent_names, parent_addresses = _get_parent_personal_data(call_record)
    all_parent_data = parent_phones | parent_names | parent_addresses

    extracted = call_record.get("extracted_intel") or {}
    mid_logs = extracted.get("mid_call_logs") or []

    identifiers: List[SuspectIdentifier] = []
    seen_keys = set()

    # 1. Process mid_call_logs if available (has richer log_intel fields)
    for log in mid_logs:
        if not isinstance(log, dict):
            continue
        kind = str(log.get("type") or log.get("kind") or "identifier").lower()
        val_norm = str(log.get("normalized_value") or log.get("value") or "").strip()
        val_raw = str(log.get("value_as_heard") or log.get("value_raw") or val_norm).strip()
        if not val_norm:
            continue
        # Exclude parent phone numbers, names, addresses
        if val_norm in all_parent_data or val_raw in all_parent_data:
            continue
        if kind == "phone" and val_norm in parent_phones:
            continue

        dedup_key = (kind, val_norm)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        sec = log.get("seconds_from_start")
        if sec is None:
            sec = log.get("timestamp")
        quote = log.get("quote")
        if quote is not None:
            quote = str(quote).strip()[:120]
            for p_val in all_parent_data:
                if p_val and len(p_val) >= 3:
                    quote = quote.replace(p_val, "[REDACTED]")
        elicitation = log.get("elicitation")
        if elicitation is not None:
            elicitation = str(elicitation).strip()

        identifiers.append(
            SuspectIdentifier(
                kind=kind,
                value_normalized=val_norm,
                value_raw=val_raw if val_raw != val_norm else val_norm,
                seconds_from_start=float(sec) if isinstance(sec, (int, float)) else None,
                quote=quote if quote else None,
                elicitation=elicitation if elicitation else None,
                status="suspected",
            )
        )

    # 2. Backfill from standard extracted_intel lists (for older records without mid_call_logs)
    kind_mappings = [
        ("upi", "upi_ids"),
        ("account", "bank_accounts"),
        ("account", "account_numbers"),
        ("ifsc", "ifsc_codes"),
        ("phone", "phone_numbers"),
        ("link", "links"),
    ]
    for kind, field_name in kind_mappings:
        for val in extracted.get(field_name, []):
            val_norm = str(val).strip()
            if not val_norm:
                continue
            if val_norm in all_parent_data:
                continue
            if kind == "phone" and (val_norm == caller_num or val_norm in parent_phones):
                continue
            dedup_key = (kind, val_norm)
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                identifiers.append(
                    SuspectIdentifier(
                        kind=kind,
                        value_normalized=val_norm,
                        value_raw=val_norm,
                        status="suspected",
                    )
                )

    return identifiers


def resolve_chakshu_category(call_record: Dict[str, Any]) -> str:
    """Map CallRecord characteristics to an approved Chakshu category."""
    summary = str(call_record.get("summary") or "").lower()
    transcript_str = str(call_record.get("transcript") or "").lower()
    combined = summary + " " + transcript_str

    if any(k in combined for k in ["arrest", "police", "cbi", "crime branch", "ed officer", "warrant"]):
        return CHAKSHU_CATEGORY_MAPPING["digital_arrest"]
    elif any(k in combined for k in ["customs", "narcotics", "mdma", "parcel seized", "illegal passport"]):
        return CHAKSHU_CATEGORY_MAPPING["customs"]
    elif any(k in combined for k in ["kyc", "sim block", "trai", "account blocked", "aadhar update"]):
        return CHAKSHU_CATEGORY_MAPPING["kyc"]
    elif any(k in combined for k in ["electricity", "power cut", "bijli", "meter"]):
        return CHAKSHU_CATEGORY_MAPPING["electricity"]
    elif any(k in combined for k in ["courier", "delivery", "amazon parcel", "flipkart parcel"]):
        return CHAKSHU_CATEGORY_MAPPING["courier"]
    elif any(k in combined for k in ["telegram task", "part time", "youtube like", "work from home"]):
        return CHAKSHU_CATEGORY_MAPPING["job"]
    elif any(k in combined for k in ["lottery", "kbc", "prize", "jackpot"]):
        return CHAKSHU_CATEGORY_MAPPING["lottery"]
    elif any(k in combined for k in ["accident", "hospital advance", "icu", "stranded nephew"]):
        return CHAKSHU_CATEGORY_MAPPING["relative"]
    return CHAKSHU_CATEGORY_MAPPING["general"]


def build_chakshu_description(call_record: Dict[str, Any]) -> str:
    """Builds a formatted incident description strictly from CallRecord facts."""
    call_id = str(call_record.get("call_id") or "unknown")
    caller_num = str(call_record.get("caller_number") or "withheld")
    duration = int(call_record.get("duration", 0) or 0)
    verdict = str(call_record.get("verdict") or "unsure")
    summary = str(call_record.get("summary") or "Suspect telecom call intercepted.")

    parent_phones, parent_names, parent_addresses = _get_parent_personal_data(call_record)
    for p_val in list(parent_phones | parent_names | parent_addresses):
        if p_val and len(p_val) >= 3:
            summary = summary.replace(p_val, "[REDACTED]")

    identifiers = _extract_suspect_identifiers(call_record)
    if identifiers:
        id_strs = [f"{i.kind}: {i.value_normalized}" for i in identifiers]
        id_summary = ", ".join(id_strs)
    else:
        id_summary = "None captured"

    return CHAKSHU_DESCRIPTION_TEMPLATE.format(
        call_id=call_id,
        caller_number=caller_num,
        duration_s=duration,
        verdict=verdict,
        identifiers_summary=id_summary,
        summary=summary,
    )


def build_chakshu_packet(call_record: Dict[str, Any]) -> ChakshuPacket:
    """Builds a formatted Chakshu citizen reporting packet from a CallRecord."""
    call_id = str(call_record.get("call_id") or "")
    caller_num = str(call_record.get("caller_number") or "")
    transcript = call_record.get("transcript") or []
    recording_url = str(call_record.get("call_recording_url") or call_record.get("recording_url") or "")
    start_time = str(call_record.get("start_time") or "2026-10-20T00:00:00Z")
    duration = int(call_record.get("duration", 0) or 0)
    money_lost = bool(call_record.get("money_lost", False))
    evidence_status = str(call_record.get("evidence_status") or "draft")

    identifiers = _extract_suspect_identifiers(call_record)
    category = resolve_chakshu_category(call_record)
    description = build_chakshu_description(call_record)
    ev_hash = compute_evidence_hash(transcript, recording_url, caller_num)

    return ChakshuPacket(
        call_id=call_id,
        caller_number=caller_num,
        category=category,
        incident_timestamp=start_time,
        duration_seconds=duration,
        suspect_identifiers=identifiers,
        evidence_summary=description,
        money_lost=money_lost,
        evidence_hash_sha256=ev_hash,
        evidence_status=evidence_status,
        verification_status="VERIFIED",
    )


def build_report_suspect_packets(call_record: Dict[str, Any]) -> List[ReportSuspectPacket]:
    """
    Builds per-identifier Report Suspect packets for financial and intermediary takedowns.
    Includes only available fields from log_intel; older records omit missing fields.
    """
    chakshu = build_chakshu_packet(call_record)
    packets = []
    for ident in chakshu.suspect_identifiers:
        packets.append(
            ReportSuspectPacket(
                portal="Report Suspect / Financial Intermediary",
                status="suspected",
                kind=ident.kind,
                value_normalized=ident.value_normalized,
                value_raw=ident.value_raw or ident.value_normalized,
                associated_call_id=chakshu.call_id,
                caller_phone=chakshu.caller_number,
                context=chakshu.evidence_summary,
                evidence_hash_sha256=chakshu.evidence_hash_sha256,
                seconds_from_start=ident.seconds_from_start,
                quote=ident.quote,
                elicitation=ident.elicitation,
            )
        )
    return packets


def build_1930_report(call_record: Dict[str, Any]) -> Optional[str]:
    """
    Generates the pre-filled 1930 Cybercrime Incident Report ONLY if money_lost is true.
    Returns null / None if money_lost is false.
    """
    if not bool(call_record.get("money_lost", False)):
        return None
    return generate_1930_report(call_record)
