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
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SuspectIdentifier(BaseModel):
    kind: str = Field(description="upi, phone, account, ifsc, or link")
    value: str = Field(description="Normalized suspect identifier value")
    first_heard_turn: Optional[int] = Field(default=None, description="Turn index where first captured")


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
    verification_status: str = "VERIFIED"


class ReportSuspectPacket(BaseModel):
    portal: str = "Report Suspect / Financial Intermediary"
    identifier_type: str
    identifier_value: str
    associated_call_id: str
    caller_phone: str
    context: str
    evidence_hash_sha256: str


def compute_evidence_hash(transcript: str, recording_url: Optional[str], caller_number: str) -> str:
    """Computes a SHA-256 integrity hash over call evidence components."""
    hasher = hashlib.sha256()
    hasher.update((caller_number or "").strip().encode("utf-8"))
    hasher.update(b"|")
    hasher.update((recording_url or "").strip().encode("utf-8"))
    hasher.update(b"|")
    hasher.update((transcript or "").strip().encode("utf-8"))
    return hasher.hexdigest()


def build_chakshu_packet(call_record: Dict[str, Any]) -> ChakshuPacket:
    """Builds a formatted Chakshu citizen reporting packet from a CallRecord."""
    call_id = call_record.get("call_id", "")
    caller_num = call_record.get("caller_number", "")
    transcript = call_record.get("transcript", "")
    recording_url = call_record.get("recording_url", "")
    start_time = call_record.get("start_time", "")
    duration = int(call_record.get("duration", 0) or 0)
    summary = call_record.get("summary") or "Suspect telecom scam call intercepted by GuardianLine."
    extracted = call_record.get("extracted_intel") or {}

    # Gather identifiers
    identifiers = []
    for upi in extracted.get("upi_ids", []):
        identifiers.append(SuspectIdentifier(kind="upi", value=str(upi)))
    for acct in extracted.get("account_numbers", []):
        identifiers.append(SuspectIdentifier(kind="account", value=str(acct)))
    for ifsc in extracted.get("ifsc_codes", []):
        identifiers.append(SuspectIdentifier(kind="ifsc", value=str(ifsc)))
    for phone in extracted.get("phone_numbers", []):
        if phone != caller_num:
            identifiers.append(SuspectIdentifier(kind="phone", value=str(phone)))
    for link in extracted.get("links", []):
        identifiers.append(SuspectIdentifier(kind="link", value=str(link)))

    # Determine category
    verdict = call_record.get("verdict", "scam")
    category = "Suspected Fraud / Telecom Abuse"
    text_lower = (transcript + " " + summary).lower()
    if "arrest" in text_lower or "police" in text_lower or "cbi" in text_lower:
        category = "Digital Arrest / Impersonation of Law Enforcement"
    elif "kyc" in text_lower or "bank" in text_lower:
        category = "Bank / KYC Suspension Fraud"
    elif "electricity" in text_lower or "power" in text_lower:
        category = "Electricity / Utility Disconnection Threat"
    elif "delivery" in text_lower or "parcel" in text_lower:
        category = "Courier / Delivery OTP Extortion"
    elif "job" in text_lower or "task" in text_lower:
        category = "Part-Time Job / Task Advance Fraud"

    ev_hash = compute_evidence_hash(transcript, recording_url, caller_num)

    return ChakshuPacket(
        call_id=call_id,
        caller_number=caller_num,
        category=category,
        incident_timestamp=start_time or "2026-10-20T00:00:00Z",
        duration_seconds=duration,
        suspect_identifiers=identifiers,
        evidence_summary=summary,
        money_lost=False,
        evidence_hash_sha256=ev_hash,
    )


def build_report_suspect_packets(call_record: Dict[str, Any]) -> List[ReportSuspectPacket]:
    """Builds per-identifier Report Suspect packets for intermediary takedowns."""
    chakshu = build_chakshu_packet(call_record)
    packets = []
    for ident in chakshu.suspect_identifiers:
        packets.append(
            ReportSuspectPacket(
                identifier_type=ident.kind,
                identifier_value=ident.value,
                associated_call_id=chakshu.call_id,
                caller_phone=chakshu.caller_number,
                context=chakshu.evidence_summary,
                evidence_hash_sha256=chakshu.evidence_hash_sha256,
            )
        )
    return packets
